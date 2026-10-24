from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import threading
import re
from core.db import db
from core.config import settings
from resolver.detector import inspect_url, detect_page
from downloader.direct import download_direct
from downloader.ffmpeg import download_hls, ffmpeg_available
from providers.netshort import NetShortProvider
from providers.tiktok import TikTokShortDramaProvider
from providers.flextv import FlexTVProvider
from providers.dramabox import DramaBoxProvider
from core.crawler import dynamic_delay_sync
import asyncio

def safe(s):
    return re.sub(r'[\\/:*?"<>|]+','_',s).strip()[:100] or "ShortDrama"

class DownloadQueue:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=settings.concurrency)
        self.cancelled = set()
        self.lock = threading.Lock()

    def update_concurrency(self, new_workers: int):
        with self.lock:
            val = max(1, min(10, int(new_workers)))
            if hasattr(self.executor, "_max_workers"):
                self.executor._max_workers = val

    def start(self):
        db.init()

    def ffmpeg_available(self):
        return ffmpeg_available()

    def add(self,url,title,episode,quality):
        tid=db.add_task(url,title,episode,quality)
        self.executor.submit(self._run,tid)
        return db.get_task(tid)

    def cancel(self,tid):
        with self.lock: self.cancelled.add(tid)
        db.update_task(tid,status="cancelled")
        return True

    def cancel_all(self):
        tids = db.cancel_all_active_tasks()
        with self.lock:
            for tid in tids:
                self.cancelled.add(tid)
        return len(tids)

    def retry(self,tid):
        with self.lock:
            if tid in self.cancelled:
                self.cancelled.remove(tid)
        db.reset_task_for_retry(tid)
        task = db.get_task(tid)
        if task:
            self.executor.submit(self._run, tid)
            return task
        return None

    def retry_all_failed(self):
        tids = db.retry_all_failed_tasks()
        with self.lock:
            for tid in tids:
                self.cancelled.discard(tid)
        for tid in tids:
            self.executor.submit(self._run, tid)
        return len(tids)

    def interactive_retry(self, tid):
        with self.lock:
            if tid in self.cancelled:
                self.cancelled.remove(tid)
        task = db.get_task(tid)
        if not task: return None
        db.update_task(tid, status="running", progress=0, error="")
        self.executor.submit(self._run_interactive, tid)
        return db.get_task(tid)

    def _run_interactive(self, tid):
        task = db.get_task(tid)
        if not task: return
        try:
            tiktok = TikTokShortDramaProvider()
            src = asyncio.run(tiktok.interactive_sniff(task["url"], timeout=90))
            if not src:
                raise RuntimeError("桌面瀏覽器超時或未捕捉到正片串流 (請在視窗內滑過拼圖)")
            ext = ".mp4"
            outdir = settings.download_dir / safe(task["title"])
            out = outdir / f"Episode_{int(task['episode']):03d}{ext}"
            path = download_direct(src.url, out, src.referer, lambda p: self._progress(tid, p))
            db.update_task(tid, status="completed", progress=100, output=str(path))
        except Exception as e:
            db.update_task(tid, status="failed", error=str(e))
        finally:
            t = db.get_task(tid)
            if t: db.add_history(t)

    def _progress(self,tid,p):
        db.update_task(tid,progress=float(p))

    def _run(self,tid):
        task=db.get_task(tid)
        if not task: return

        # Check if already downloaded on disk
        ext = ".mp4"
        outdir = settings.download_dir / safe(task["title"])
        out = outdir / f"Episode_{int(task['episode']):03d}{ext}"
        if out.exists() and out.stat().st_size > 500 * 1024:
            db.update_task(tid, status="completed", progress=100, output=str(out))
            t = db.get_task(tid)
            if t: db.add_history(t)
            return

        db.update_task(tid,status="running",progress=0)
        try:
            if tid in self.cancelled: raise RuntimeError("task cancelled")

            # Dynamic crawler delay to avoid rate limiting
            dynamic_delay_sync()

            src=inspect_url(task["url"], task["url"])

            # If not a direct media link, try resolving via provider or detect_page
            if not src or src.kind not in ("direct", "hls"):
                netshort = NetShortProvider()
                tiktok = TikTokShortDramaProvider()
                flextv = FlexTVProvider()
                dramabox = DramaBoxProvider()
                if netshort.can_handle(task["url"]):
                    try:
                        drama = netshort.get_drama(task["url"])
                        if drama.title and (task["title"] == "ShortDrama" or not task["title"]):
                            task["title"] = drama.title
                            db.update_task(tid, title=drama.title)
                    except Exception:
                        pass
                    src = asyncio.run(netshort.resolve_video_url(task["url"]))
                elif tiktok.can_handle(task["url"]):
                    try:
                        drama = tiktok.get_drama(task["url"])
                        if drama.title and (task["title"] == "ShortDrama" or not task["title"]):
                            task["title"] = drama.title
                            db.update_task(tid, title=drama.title)
                    except Exception:
                        pass
                    src = asyncio.run(tiktok.resolve_video_url(task["url"]))
                elif flextv.can_handle(task["url"]):
                    try:
                        drama = flextv.get_drama(task["url"])
                        if drama.title and (task["title"] == "ShortDrama" or not task["title"]):
                            task["title"] = drama.title
                            db.update_task(tid, title=drama.title)
                    except Exception:
                        pass
                    src = asyncio.run(flextv.resolve_video_url(task["url"]))
                elif dramabox.can_handle(task["url"]):
                    try:
                        drama = dramabox.get_drama(task["url"])
                        if drama.title and (task["title"] == "ShortDrama" or not task["title"]):
                            task["title"] = drama.title
                            db.update_task(tid, title=drama.title)
                    except Exception:
                        pass
                    src = asyncio.run(dramabox.resolve_video_url(task["url"]))

            if not src or src.kind not in ("direct", "hls"):
                candidates = asyncio.run(detect_page(task["url"], timeout=30))
                if candidates:
                    src = candidates[0]

            if not src: raise RuntimeError("無法取得媒體來源")
            ext=".mp4"
            if src.kind=="direct":
                ext=".webm" if "webm" in src.content_type else ".mp4"
            outdir=settings.download_dir/safe(task["title"])
            out=outdir/f"Episode_{int(task['episode']):03d}{ext}"
            if src.kind=="direct":
                path=download_direct(src.url,out,src.referer,lambda p:self._progress(tid,p))
            elif src.kind=="hls":
                path=download_hls(src.url,out,task["quality"],lambda p:self._progress(tid,p))
            else:
                raise RuntimeError("目前 v3.4 尚未自動下載 DASH，請使用可取得的 MP4/HLS 來源")
            db.update_task(tid,status="completed",progress=100,output=str(path))
        except Exception as e:
            db.update_task(tid,status="failed",error=str(e))
        finally:
            task=db.get_task(tid)
            if task:
                db.add_history(task)

queue=DownloadQueue()
