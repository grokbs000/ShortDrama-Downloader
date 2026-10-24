import argparse
import asyncio
from resolver.detector import detect_page
from resolver.hls import inspect_hls
from downloader.direct import download_direct
from downloader.ffmpeg import download_hls

def main():
    p = argparse.ArgumentParser(description="ShortDrama Downloader v3.4")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("direct")
    d.add_argument("url")
    d.add_argument("-o", "--output")

    x = sub.add_parser("detect")
    x.add_argument("url")
    x.add_argument("--timeout", type=int, default=60)

    h = sub.add_parser("hls")
    h.add_argument("url")
    h.add_argument("--quality", default="best")
    h.add_argument("-o", "--output")

    dl = sub.add_parser("download", help="Universal download with auto detection/provider")
    dl.add_argument("url")
    dl.add_argument("-t", "--title", default="")
    dl.add_argument("-e", "--episode", type=int, default=1)
    dl.add_argument("-q", "--quality", default="best")
    dl.add_argument("-o", "--output")

    ns = sub.add_parser("netshort", help="NetShort drama parser and downloader")
    ns.add_argument("url", help="NetShort drama or episode URL")
    ns.add_argument("--info", action="store_true", help="Print drama info and episodes")
    ns.add_argument("--all-free", action="store_true", help="Download all unlocked episodes")
    ns.add_argument("--episodes", help="Episode numbers to download, e.g. 1,2,3 or 1-5")
    ns.add_argument("-q", "--quality", default="best")

    tk = sub.add_parser("tiktok", help="TikTok ShortDrama parser and downloader")
    tk.add_argument("url", help="TikTok shortdrama episode URL")
    tk.add_argument("--info", action="store_true", help="Print drama info and episodes")
    tk.add_argument("--all", action="store_true", help="Download all episodes")
    tk.add_argument("--episodes", help="Episode numbers to download, e.g. 1,2,3 or 1-5")
    tk.add_argument("-q", "--quality", default="best")

    lg = sub.add_parser("login", help="Open browser to login and save session for locked/paid episodes")
    lg.add_argument("site", choices=["netshort", "tiktok"], default="netshort", nargs="?")

    a = p.parse_args()

    if a.cmd == "direct":
        out = a.output or "downloads/video.mp4"
        print(download_direct(a.url, out, None))
    elif a.cmd == "detect":
        items = asyncio.run(detect_page(a.url, a.timeout))
        for i, c in enumerate(items, 1):
            print(f"[{i}] {c.kind:7} score={c.score:4} type={c.content_type} {c.url}")
    elif a.cmd == "hls":
        info = inspect_hls(a.url)
        print(info.to_dict())
        out = a.output or "downloads/video.mp4"
        print(download_hls(a.url, out, a.quality))
    elif a.cmd == "download":
        from downloader.queue import queue
        from core.db import db
        import time
        queue.start()
        task = queue.add(a.url, a.title or "ShortDrama", a.episode, a.quality)
        print(f"Task #{task['id']} started. Waiting for completion...")
        while True:
            t = db.get_task(task["id"])
            if t["status"] == "completed":
                print(f"Download completed: {t.get('output')}")
                break
            elif t["status"] in ("failed", "cancelled"):
                print(f"Task {t['status']}: {t.get('error')}")
                break
            time.sleep(1)
    elif a.cmd == "netshort":
        from providers.netshort import NetShortProvider
        from downloader.queue import queue
        from core.db import db
        import time
        p = NetShortProvider()
        drama = p.get_drama(a.url)
        print(f"=== {drama.title} (ID: {drama.drama_id}) ===")
        print(f"Total Episodes: {drama.total_episodes} | Unlocked: {len([e for e in drama.episodes if not e.is_locked])}")
        if a.info or (not a.all_free and not a.episodes):
            print("Episodes:")
            for ep in drama.episodes:
                lock_str = "🔒 Locked" if ep.is_locked else "🔓 Free"
                print(f"  EP {ep.episode_no:02d} [{lock_str}] -> {ep.page_url}")
            if not a.all_free and not a.episodes:
                return

        targets = []
        if a.all_free:
            targets = [e for e in drama.episodes if not e.is_locked]
        elif a.episodes:
            selected_nos = set()
            for part in a.episodes.split(","):
                if "-" in part:
                    s, e = part.split("-")
                    selected_nos.update(range(int(s), int(e) + 1))
                elif part.isdigit():
                    selected_nos.add(int(part))
            targets = [e for e in drama.episodes if e.episode_no in selected_nos]

        print(f"Queueing {len(targets)} episodes for download...")
        queue.start()
        task_ids = []
        for ep in targets:
            t = queue.add(ep.page_url, drama.title, ep.episode_no, a.quality)
            task_ids.append(t["id"])
            print(f"  Added EP {ep.episode_no} as Task #{t['id']}")

        print("Waiting for tasks in queue...")
        while task_ids:
            done = []
            for tid in task_ids:
                t = db.get_task(tid)
                if t["status"] in ("completed", "failed", "cancelled"):
                    done.append(tid)
                    print(f"Task #{tid} (EP {t['episode']}): {t['status']} -> {t.get('output') or t.get('error')}")
            for d in done: task_ids.remove(d)
            if task_ids: time.sleep(1)
    elif a.cmd == "tiktok":
        from providers.tiktok import TikTokShortDramaProvider
        from downloader.queue import queue
        from core.db import db
        import time
        p = TikTokShortDramaProvider()
        drama = p.get_drama(a.url)
        print(f"=== {drama.title} (ID: {drama.drama_id}) ===")
        print(f"Total Episodes: {drama.total_episodes}")
        if a.info or (not a.all and not a.episodes):
            print("Episodes:")
            for ep in drama.episodes[:30]:
                print(f"  EP {ep.episode_no:02d} -> {ep.page_url}")
            if len(drama.episodes) > 30:
                print(f"  ... 以及其他 {len(drama.episodes) - 30} 集")
            if not a.all and not a.episodes:
                return

        targets = []
        if a.all:
            targets = drama.episodes
        elif a.episodes:
            selected_nos = set()
            for part in a.episodes.split(","):
                if "-" in part:
                    s, e = part.split("-")
                    selected_nos.update(range(int(s), int(e) + 1))
                elif part.isdigit():
                    selected_nos.add(int(part))
            targets = [e for e in drama.episodes if e.episode_no in selected_nos]

        print(f"Queueing {len(targets)} episodes for download...")
        queue.start()
        task_ids = []
        for ep in targets:
            t = queue.add(ep.page_url, drama.title, ep.episode_no, a.quality)
            task_ids.append(t["id"])
            print(f"  Added EP {ep.episode_no} as Task #{t['id']}")

        print("Waiting for tasks in queue...")
        while task_ids:
            done = []
            for tid in task_ids:
                t = db.get_task(tid)
                if t["status"] in ("completed", "failed", "cancelled"):
                    done.append(tid)
                    print(f"Task #{tid} (EP {t['episode']}): {t['status']} -> {t.get('output') or t.get('error')}")
            for d in done: task_ids.remove(d)
            if task_ids: time.sleep(1)
    elif a.cmd == "login":
        from playwright.sync_api import sync_playwright
        from pathlib import Path
        site = a.site or "netshort"
        save_path = Path(f"data/auth_{site}.json")
        save_path.parent.mkdir(parents=True, exist_ok=True)
        login_url = "https://netshort.com/zh" if site == "netshort" else "https://www.tiktok.com/login"
        print(f"正在啟動瀏覽器進行 {site.upper()} 登入...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.goto(login_url)
            input(f"登入完成並確認已可觀看後，請在此處終端機按 [Enter] 儲存登入憑證...")
            context.storage_state(path=str(save_path))
            browser.close()
        print(f"登入狀態已儲存至 {save_path}！後續下載將自動套用此帳號權限。")

if __name__ == "__main__":
    main()
