from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from pydantic import BaseModel
from pathlib import Path
import asyncio
import csv
import io

from core.config import settings
from core.db import db
from providers.generic import GenericProvider
from providers.dramabos import DramaBosProvider
from providers.netshort import NetShortProvider
from resolver.detector import detect_page
from resolver.hls import inspect_hls
from downloader.queue import queue
from exports.csv_export import export_tasks_csv, export_episodes_csv

app = FastAPI(title="ShortDrama Downloader v3.4", version="3.4.0")
generic = GenericProvider()
netshort = NetShortProvider()

class DetectRequest(BaseModel):
    url: str
    timeout: int = 60

class DownloadRequest(BaseModel):
    url: str
    title: str = "ShortDrama"
    episode: int = 1
    quality: str = "best"

class BatchRequest(BaseModel):
    urls: list[str]
    title: str = "ShortDrama"
    start_episode: int = 1
    quality: str = "best"

class DramaInfoRequest(BaseModel):
    url: str

class DramaBatchDownloadRequest(BaseModel):
    title: str
    quality: str = "best"
    episodes: list[dict]
    skip_downloaded: bool = True

class BatchDramasDownloadRequest(BaseModel):
    urls: list[str]
    quality: str = "best"
    only_first_episode: bool = False
    skip_downloaded: bool = True

class HLSRequest(BaseModel):
    url: str
    quality: str = "best"

class DramaBosSearchRequest(BaseModel):
    keyword: str

class SettingsUpdateRequest(BaseModel):
    download_dir: str = None
    crawler_delay_min: float = None
    crawler_delay_max: float = None
    concurrency: int = None

class AuthSaveRequest(BaseModel):
    provider: str
    auth_data: str

class AuthClearRequest(BaseModel):
    provider: str

@app.on_event("startup")
async def startup():
    db.init()
    queue.start()

@app.get("/", response_class=HTMLResponse)
def index():
    return (Path(__file__).parent / "web" / "index.html").read_text(encoding="utf-8")

@app.get("/api/health")
def health():
    return {"ok": True, "version": "3.4.0", "ffmpeg": queue.ffmpeg_available()}

from providers.tiktok import TikTokShortDramaProvider
from providers.flextv import FlexTVProvider
from providers.dramabox import DramaBoxProvider
tiktok = TikTokShortDramaProvider()
flextv = FlexTVProvider()
dramabox = DramaBoxProvider()

@app.post("/api/drama/info")
def drama_info(req: DramaInfoRequest):
    url = req.url.strip()
    if netshort.can_handle(url):
        try:
            info = netshort.get_drama(url)
            return {"provider": "netshort", "drama": info.to_dict()}
        except Exception as e:
            raise HTTPException(400, f"NetShort 解析失敗: {e}")
    elif tiktok.can_handle(url):
        try:
            info = tiktok.get_drama(url)
            return {"provider": "tiktok", "drama": info.to_dict()}
        except Exception as e:
            raise HTTPException(400, f"TikTok 解析失敗: {e}")
    elif flextv.can_handle(url):
        try:
            info = flextv.get_drama(url)
            return {"provider": "flextv", "drama": info.to_dict()}
        except Exception as e:
            raise HTTPException(400, f"FlexTV 解析失敗: {e}")
    elif dramabox.can_handle(url):
        try:
            info = dramabox.get_drama(url)
            return {"provider": "dramabox", "drama": info.to_dict()}
        except Exception as e:
            raise HTTPException(400, f"DramaBox 解析失敗: {e}")
    raise HTTPException(400, "目前此平台尚未提供結構化劇集解析，請直接使用偵測或直鏈下載")

class DramaStreamRequest(BaseModel):
    url: str
    episode_no: int = 1
    title: str = "ShortDrama"

@app.post("/api/drama/stream")
async def drama_stream(req: DramaStreamRequest):
    import urllib.parse
    import re
    import logging
    logger = logging.getLogger("stream")

    url = req.url.strip()
    if not url:
        raise HTTPException(400, "未提供有效的集數 URL")

    safe_title = re.sub(r'[\\/:*?"<>|]+', '_', req.title).strip()[:100] or "ShortDrama"
    logger.info(f"[Stream] ep={req.episode_no} title={safe_title} url={url[:80]}")

    # 1. Check local file first (instant playback)
    local_file = settings.download_dir / safe_title / f"Episode_{int(req.episode_no):03d}.mp4"
    if local_file.exists() and local_file.stat().st_size > 100 * 1024:
        logger.info(f"[Stream] Found local: {local_file}")
        return {
            "ok": True,
            "kind": "local",
            "url": f"/api/file?path={urllib.parse.quote(str(local_file))}",
            "is_local": True
        }

    # 2. Provider-specific fast-path resolve
    src = None

    # DramaBox: episodes already contain direct video/m3u8 URLs
    if dramabox.can_handle(url):
        try:
            drama = dramabox.get_drama(url)
            for ep in drama.episodes:
                if ep.episode_no == req.episode_no:
                    stream_url = ep.video_url or ep.m3u8_url
                    kind = "direct" if ep.video_url else "hls"
                    if stream_url:
                        logger.info(f"[Stream] DramaBox direct: {kind}")
                        return {"ok": True, "kind": kind, "url": stream_url, "is_local": False}
        except Exception as e:
            logger.warning(f"[Stream] DramaBox fast-path failed: {e}")

    # NetShort → Playwright sniff
    if not src and netshort.can_handle(url):
        try:
            src = await netshort.resolve_video_url(url)
        except Exception as e:
            logger.warning(f"[Stream] NetShort resolve failed: {e}")

    # FlexTV → API/Playwright
    if not src and flextv.can_handle(url):
        try:
            src = await flextv.resolve_video_url(url)
        except Exception as e:
            logger.warning(f"[Stream] FlexTV resolve failed: {e}")

    # TikTok → Playwright sniff (may need interactive_sniff for some)
    if not src and tiktok.can_handle(url):
        try:
            src = await tiktok.resolve_video_url(url)
        except Exception as e:
            logger.warning(f"[Stream] TikTok resolve failed: {e}")
        if not src:
            try:
                src = await tiktok.interactive_sniff(url, timeout=45)
            except Exception as e:
                logger.warning(f"[Stream] TikTok interactive_sniff failed: {e}")

    # 3. Generic fallback: detector
    if not src:
        try:
            from resolver.detector import detect_page
            candidates = await detect_page(url, timeout=20)
            if candidates:
                src = candidates[0]
                logger.info(f"[Stream] Detector fallback found: {src.kind}")
        except Exception as e:
            logger.warning(f"[Stream] Detector fallback failed: {e}")

    if src:
        return {
            "ok": True,
            "kind": src.kind,
            "url": src.url,
            "is_local": False
        }

    raise HTTPException(400, "目前無法即時取得此集之可播放串流，請稍候重試或加入下載隊列")

@app.get("/api/tiktok/catalog")
def tiktok_catalog(offset: int = 0, limit: int = 24, refresh: bool = False):
    try:
        res = tiktok.fetch_catalog(offset=offset, limit=limit, force_refresh=refresh)
        return {"ok": True, **res}
    except Exception as e:
        raise HTTPException(500, f"無法同步 TikTok 短劇列表: {e}")

@app.get("/api/flextv/catalog")
def flextv_catalog(offset: int = 0, limit: int = 24, refresh: bool = False):
    try:
        res = flextv.fetch_catalog(offset=offset, limit=limit, force_refresh=refresh)
        return {"ok": True, **res}
    except Exception as e:
        raise HTTPException(500, f"無法同步 Flex TV 短劇列表: {e}")

@app.get("/api/dramabox/catalog")
def dramabox_catalog(offset: int = 0, limit: int = 24, refresh: bool = False):
    try:
        res = dramabox.fetch_catalog(offset=offset, limit=limit, force_refresh=refresh)
        return {"ok": True, **res}
    except Exception as e:
        raise HTTPException(500, f"無法同步 DramaBox 短劇列表: {e}")

@app.get("/api/netshort/catalog")
def netshort_catalog(offset: int = 0, limit: int = 24, refresh: bool = False):
    try:
        res = netshort.fetch_catalog(offset=offset, limit=limit, force_refresh=refresh)
        return {"ok": True, **res}
    except Exception as e:
        raise HTTPException(500, f"無法同步 NetShort 短劇列表: {e}")

@app.get("/api/downloads/downloaded_map")
def get_downloaded_map():
    return db.get_downloaded_map()

@app.post("/api/drama/batch_download")
def drama_batch_download(req: DramaBatchDownloadRequest):
    downloaded_map = db.get_downloaded_map() if req.skip_downloaded else None
    completed_urls = set(downloaded_map["completed_urls"]) if downloaded_map else set()
    downloaded_eps = set(downloaded_map["drama_episodes"].get(req.title, [])) if downloaded_map else set()

    results = []
    skipped = 0
    for item in req.episodes:
        ep_url = item.get("page_url") or item.get("url")
        ep_no = int(item.get("episode_no") or item.get("episode") or 1)
        if not ep_url:
            continue
        if req.skip_downloaded and (ep_url in completed_urls or ep_no in downloaded_eps):
            skipped += 1
            continue
        t = queue.add(ep_url, req.title, ep_no, req.quality)
        results.append(t)
    return {"tasks": results, "count": len(results), "skipped": skipped}

@app.post("/api/drama/batch_dramas_download")
def batch_dramas_download(req: BatchDramasDownloadRequest):
    from core.crawler import dynamic_delay_sync
    downloaded_map = db.get_downloaded_map() if req.skip_downloaded else None
    completed_urls = set(downloaded_map["completed_urls"]) if downloaded_map else set()

    queued_tasks = []
    skipped_count = 0
    failed_dramas = []

    for drama_url in req.urls:
        url = drama_url.strip()
        if not url: continue
        drama_info_obj = None
        try:
            if netshort.can_handle(url):
                drama_info_obj = netshort.get_drama(url)
            elif tiktok.can_handle(url):
                drama_info_obj = tiktok.get_drama(url)
            elif flextv.can_handle(url):
                drama_info_obj = flextv.get_drama(url)
            elif dramabox.can_handle(url):
                drama_info_obj = dramabox.get_drama(url)
        except Exception as e:
            failed_dramas.append({"url": url, "error": str(e)})
            continue

        if not drama_info_obj:
            failed_dramas.append({"url": url, "error": "不支援的平台網址"})
            continue

        d_title = drama_info_obj.title
        eps = drama_info_obj.episodes
        if req.only_first_episode and eps:
            eps = [eps[0]]

        downloaded_eps = set(downloaded_map["drama_episodes"].get(d_title, [])) if downloaded_map else set()

        for ep in eps:
            if getattr(ep, "is_locked", False):
                continue
            ep_page_url = getattr(ep, "page_url", "")
            ep_no = getattr(ep, "episode_no", 1)
            if not ep_page_url:
                continue
            if req.skip_downloaded and (ep_page_url in completed_urls or ep_no in downloaded_eps):
                skipped_count += 1
                continue
            t = queue.add(ep_page_url, d_title, ep_no, req.quality)
            queued_tasks.append(t)

        # Dynamic jitter rate limit delay between drama resolutions
        dynamic_delay_sync()

    return {
        "queued_count": len(queued_tasks),
        "skipped_count": skipped_count,
        "failed_dramas": failed_dramas
    }

@app.post("/api/detect")
async def detect(req: DetectRequest):
    try:
        candidates = await detect_page(req.url, req.timeout)
        return {"url": req.url, "candidates": [c.to_dict() for c in candidates]}
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/hls/inspect")
def hls(req: HLSRequest):
    try:
        return inspect_hls(req.url).to_dict()
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/download")
def download(req: DownloadRequest):
    title = req.title
    episode = req.episode
    if (not title or title == "ShortDrama"):
        if netshort.can_handle(req.url):
            try:
                drama = netshort.get_drama(req.url)
                if drama.title:
                    title = drama.title
            except Exception:
                pass
        elif tiktok.can_handle(req.url):
            try:
                drama = tiktok.get_drama(req.url)
                if drama.title:
                    title = drama.title
            except Exception:
                pass
        elif dramabox.can_handle(req.url):
            try:
                drama = dramabox.get_drama(req.url)
                if drama.title:
                    title = drama.title
            except Exception:
                pass
    task = queue.add(req.url, title, episode, req.quality)
    return task

@app.post("/api/batch")
def batch(req: BatchRequest):
    result = []
    for i, url in enumerate(req.urls):
        if url.strip():
            result.append(queue.add(url.strip(), req.title, req.start_episode + i, req.quality))
    return {"tasks": result}

@app.get("/api/tasks")
def tasks():
    return db.list_tasks()

@app.get("/api/history")
def history():
    return db.list_history()

@app.post("/api/tasks/{task_id}/cancel")
def cancel(task_id: int):
    return {"ok": queue.cancel(task_id)}

@app.post("/api/tasks/{task_id}/retry")
def retry_task(task_id: int):
    task = queue.retry(task_id)
    if not task:
        raise HTTPException(404, "任務不存在或無法重試")
    return {"ok": True, "task": task}

@app.post("/api/tasks/{task_id}/sniff_retry")
def sniff_retry_task(task_id: int):
    task = queue.interactive_retry(task_id)
    if not task:
        raise HTTPException(404, "任務不存在或無法啟動桌面視窗嗅探")
    return {"ok": True, "task": task}

@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: int):
    ok = db.delete_task(task_id)
    return {"ok": ok}

@app.post("/api/tasks/clear_completed")
def clear_completed_tasks():
    ok = db.clear_completed_tasks()
    return {"ok": ok}

@app.post("/api/tasks/clear_all")
def clear_all_tasks():
    ok = db.clear_all_tasks()
    return {"ok": ok}

@app.post("/api/tasks/cancel_all")
def cancel_all_tasks_route():
    count = queue.cancel_all()
    return {"ok": True, "count": count}

@app.post("/api/tasks/retry_all_failed")
def retry_all_failed():
    count = queue.retry_all_failed()
    return {"ok": True, "count": count}

@app.post("/api/history/clear")
def clear_history():
    ok = db.clear_history()
    return {"ok": ok}

@app.get("/api/settings")
def get_settings():
    return {
        "download_dir": str(settings.download_dir),
        "download_dir_exists": settings.download_dir.exists(),
        "crawler_delay_min": settings.crawler_delay_min,
        "crawler_delay_max": settings.crawler_delay_max,
        "concurrency": settings.concurrency,
        "ffmpeg_available": queue.ffmpeg_available(),
        "host": settings.host,
        "port": settings.port
    }

@app.post("/api/settings")
def update_settings(req: SettingsUpdateRequest):
    path_str = req.download_dir.strip() if req.download_dir else None
    try:
        settings.save_settings(
            download_dir=path_str,
            crawler_delay_min=req.crawler_delay_min,
            crawler_delay_max=req.crawler_delay_max,
            concurrency=req.concurrency
        )
        if req.concurrency is not None:
            queue.update_concurrency(settings.concurrency)
        return {
            "ok": True,
            "download_dir": str(settings.download_dir),
            "download_dir_exists": settings.download_dir.exists(),
            "crawler_delay_min": settings.crawler_delay_min,
            "crawler_delay_max": settings.crawler_delay_max,
            "concurrency": settings.concurrency
        }
    except Exception as e:
        raise HTTPException(400, f"儲存設定失敗: {e}")

@app.get("/api/auth/status")
def get_auth_status():
    import datetime
    import json
    res = {}
    for prov in ("netshort", "tiktok"):
        f = Path(f"data/auth_{prov}.json")
        configured = f.exists() and f.stat().st_size > 5
        updated_at = ""
        size_bytes = 0
        if configured:
            size_bytes = f.stat().st_size
            updated_at = datetime.datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        res[prov] = {
            "configured": configured,
            "size": size_bytes,
            "updated_at": updated_at,
            "path": str(f)
        }
    return res

@app.post("/api/auth/save")
def save_auth(req: AuthSaveRequest):
    import json
    prov = req.provider.lower().strip()
    if prov not in ("netshort", "tiktok"):
        raise HTTPException(400, "不支援的平台")
    text = req.auth_data.strip()
    if not text:
        raise HTTPException(400, "憑證內容不可為空")
    
    try:
        parsed = json.loads(text)
        formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
    except Exception:
        formatted = text

    target = Path(f"data/auth_{prov}.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(formatted, encoding="utf-8")
    return {"ok": True, "message": f"{prov.capitalize()} 登錄資料已成功保存！"}

@app.post("/api/auth/clear")
def clear_auth(req: AuthClearRequest):
    prov = req.provider.lower().strip()
    target = Path(f"data/auth_{prov}.json")
    if target.exists():
        target.unlink()
    return {"ok": True, "message": f"{prov.capitalize()} 登錄資料已清除"}

@app.post("/api/auth/tiktok/browser_login")
async def browser_login_tiktok():
    from playwright.async_api import async_playwright
    import json
    auth_file = Path("data/auth_tiktok.json")
    auth_file.parent.mkdir(parents=True, exist_ok=True)
    
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(
                headless=False,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
            )
        except Exception as e:
            raise HTTPException(500, f"無法啟動桌面瀏覽器: {e}")

        try:
            context = await browser.new_context(
                viewport={"width": 1280, "height": 850},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                locale="zh-TW"
            )
            page = await context.new_page()
            try:
                from playwright_stealth import Stealth
                await Stealth().apply_stealth_async(page)
            except Exception:
                pass

            await page.goto("https://www.tiktok.com/login", wait_until="domcontentloaded")
            
            logged_in = False
            for _ in range(120):
                try:
                    cookies = await context.cookies()
                    c_names = [c["name"] for c in cookies]
                    if any(k in c_names for k in ("sessionid", "sessionid_ss", "sid_guard", "uid_tt")):
                        logged_in = True
                        state = await context.storage_state()
                        auth_file.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
                        await asyncio.sleep(1.5)
                        break
                except Exception:
                    # 瀏覽器可能已被使用者關閉
                    break
                await asyncio.sleep(1)

            if not auth_file.exists() or auth_file.stat().st_size <= 10:
                try:
                    state = await context.storage_state()
                    auth_file.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
                except Exception:
                    pass

            return {
                "ok": True,
                "logged_in": logged_in,
                "message": "🎉 TikTok 憑證與會員登入狀態已成功保存！" if logged_in else "已保存當前瀏覽器狀態與 Cookies"
            }
        finally:
            try:
                await browser.close()
            except Exception:
                pass

@app.get("/api/export/tasks.csv")
def export_tasks():
    data = export_tasks_csv()
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=download_tasks.csv"},
    )

@app.get("/api/export/episodes.csv")
def export_episodes():
    data = export_episodes_csv()
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=episodes.csv"},
    )

@app.post("/api/provider/dramabos/search")
def dramabos_search(req: DramaBosSearchRequest):
    provider = DramaBosProvider()
    if not provider.enabled:
        raise HTTPException(400, "DramaBos Provider 尚未設定 API URL / API Key")
    try:
        return provider.search(req.keyword)
    except Exception as e:
        raise HTTPException(400, str(e))

@app.get("/api/file")
def get_file(path: str = Query(...)):
    p = Path(path).expanduser().resolve()
    root = settings.download_dir.resolve()
    if root not in p.parents and p != root:
        raise HTTPException(403, "只能存取下載資料夾")
    if not p.exists() or not p.is_file():
        raise HTTPException(404, "檔案不存在")
    return FileResponse(p)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)
