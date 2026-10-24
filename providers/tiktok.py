import re
import json
import asyncio
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from providers.base import Provider
from core.models import MediaSource
from core.crawler import dynamic_delay_sync, dynamic_delay_async

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

@dataclass
class TikTokEpisode:
    episode_no: int
    item_id: str
    title: str
    is_locked: bool
    cover_url: str
    page_url: str

    def to_dict(self):
        return {
            "episode_no": self.episode_no,
            "item_id": self.item_id,
            "title": self.title,
            "is_locked": self.is_locked,
            "cover_url": self.cover_url,
            "page_url": self.page_url,
        }

@dataclass
class TikTokDrama:
    drama_id: str
    title: str
    cover_url: str
    intro: str
    total_episodes: int
    episodes: List[TikTokEpisode]
    canonical_url: str

    def to_dict(self):
        return {
            "drama_id": self.drama_id,
            "title": self.title,
            "cover_url": self.cover_url,
            "intro": self.intro,
            "total_episodes": self.total_episodes,
            "unlocked_count": len([e for e in self.episodes if not e.is_locked]),
            "episodes": [e.to_dict() for e in self.episodes],
            "canonical_url": self.canonical_url,
        }

class TikTokShortDramaProvider(Provider):
    name = "tiktok"

    def can_handle(self, url: str) -> bool:
        if not url: return False
        u = url.lower()
        return "tiktok.com" in u and ("shortdrama" in u or "short_drama" in u)

    def extract_drama_and_episode(self, url: str):
        # Match pattern: /shortdrama/episode/<drama_id>/<episode_no>
        m = re.search(r"/shortdrama/episode/(\d+)(?:/(\d+))?", url)
        if m:
            drama_id = m.group(1)
            ep_no = int(m.group(2)) if m.group(2) else 1
            return drama_id, ep_no
        return "", 1

    def get_drama(self, url: str) -> TikTokDrama:
        return asyncio.run(self._get_drama_async(url))

    async def _get_drama_async(self, url: str) -> TikTokDrama:
        await dynamic_delay_async()
        from playwright.async_api import async_playwright
        drama_id, current_ep = self.extract_drama_and_episode(url)

        auth_file = Path("data/auth_tiktok.json")
        drama_data = None
        item_list = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                ctx_args = {
                    "user_agent": UA,
                    "locale": "en-US",
                }
                if auth_file.exists():
                    ctx_args["storage_state"] = str(auth_file)
                context = await browser.new_context(**ctx_args)
                page = await context.new_page()

                async def on_resp(resp):
                    nonlocal drama_data, item_list
                    if "/api/drama/episode/item_list/" in resp.url:
                        try:
                            j = await resp.json()
                            if "itemList" in j and j["itemList"]:
                                item_list = j["itemList"]
                                if "dramaInfo" in item_list[0]:
                                    drama_data = item_list[0]["dramaInfo"]
                        except Exception:
                            pass

                page.on("response", on_resp)
                await page.goto(url, wait_until="domcontentloaded", timeout=40000)

                for _ in range(8):
                    if drama_data:
                        break
                    await asyncio.sleep(1)

            finally:
                await browser.close()

        title = "TikTok ShortDrama"
        intro = ""
        cover_url = ""
        total_eps = 1
        episodes = []

        if drama_data:
            title = drama_data.get("dramaName") or title
            intro = drama_data.get("description") or intro
            covers = drama_data.get("cover", {}).get("urlList", [])
            cover_url = covers[0] if covers else ""
            total_eps = int(drama_data.get("numVideos") or drama_data.get("totalEpisodeCount") or len(item_list) or 1)

        canonical = f"https://www.tiktok.com/shortdrama/episode/{drama_id}/1" if drama_id else url

        # Construct episode list
        for ep_i in range(1, total_eps + 1):
            ep_url = f"https://www.tiktok.com/shortdrama/episode/{drama_id}/{ep_i}" if drama_id else url
            item_match = next((it for it in item_list if it.get("dramaInfo", {}).get("DramaVideoData", {}).get("EpisodeNumber") == ep_i), None)
            ep_item_id = str(item_match.get("id", "")) if item_match else ""
            episodes.append(TikTokEpisode(
                episode_no=ep_i,
                item_id=ep_item_id,
                title=f"{title} - Episode {ep_i}",
                is_locked=False,  # TikTok shortdramas are labeled all free when logged in
                cover_url=cover_url,
                page_url=ep_url
            ))

        return TikTokDrama(
            drama_id=drama_id,
            title=title,
            cover_url=cover_url,
            intro=intro,
            total_episodes=len(episodes),
            episodes=episodes,
            canonical_url=canonical
        )

    async def resolve_video_url(self, page_url: str, timeout: int = 30) -> Optional[MediaSource]:
        """Sniff actual video stream from TikTok ShortDrama page with binary verification."""
        from playwright.async_api import async_playwright
        import requests
        from urllib.parse import quote

        auth_file = Path("data/auth_tiktok.json")
        candidates = []
        has_captcha = False
        has_login_gate = False

        def is_bad_url(u: str) -> bool:
            u_low = u.lower()
            return any(k in u_low for k in [
                "playback", "ttwstatic", "static", "login_static", "website-login",
                "captcha", "thumb", "avatar", "preview", "favicon"
            ])

        def verify_mp4_url(cand_url: str, referer: str) -> bool:
            headers = {
                "User-Agent": UA,
                "Referer": quote(referer, safe=":/%?&=#@+,"),
                "Range": "bytes=0-1023",
                "Accept": "video/avc,video/mp4,video/*;q=0.9,*/*;q=0.8",
                "Accept-Encoding": "identity"
            }
            try:
                with requests.get(cand_url, headers=headers, stream=True, timeout=8, allow_redirects=True) as resp:
                    if resp.status_code not in (200, 206):
                        return False
                    ct = (resp.headers.get("Content-Type") or "").lower()
                    if "text/html" in ct or "json" in ct:
                        return False
                    
                    # 檢查總檔案大小
                    cr = resp.headers.get("Content-Range", "")
                    cl = resp.headers.get("Content-Length", "")
                    total = 0
                    if cr and "/" in cr:
                        t_str = cr.split("/")[-1]
                        if t_str.isdigit(): total = int(t_str)
                    elif cl and cl.isdigit():
                        total = int(cl)
                    
                    # 必須大於 1MB，排除 193KB 的音符宣傳片
                    if 0 < total < 1024 * 1024:
                        return False

                    sample = resp.raw.read(64)
                    return b"ftyp" in sample
            except Exception:
                return False

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
            )
            try:
                ctx_args = {
                    "user_agent": UA,
                    "locale": "zh-TW",
                    "viewport": {"width": 1280, "height": 850}
                }
                if auth_file.exists():
                    ctx_args["storage_state"] = str(auth_file)
                context = await browser.new_context(**ctx_args)
                page = await context.new_page()

                # 嘗試套用 stealth
                try:
                    from playwright_stealth import Stealth
                    await Stealth().apply_stealth_async(page)
                except Exception:
                    pass

                async def on_resp(resp):
                    u = resp.url
                    ct = (resp.headers.get("content-type") or "").lower()
                    if is_bad_url(u):
                        return
                    if ("video/" in ct or "mpegurl" in ct or any(k in u for k in [".mp4", ".m3u8", "video/tos", "tiktokcdn.com"])) and u not in candidates:
                        candidates.append(u)

                page.on("response", on_resp)
                await page.goto(page_url, wait_until="domcontentloaded", timeout=timeout * 1000)

                # 嘗試檢查頁面狀態與點擊播放
                for _ in range(8):
                    # 檢查是否有合法的候選 URL
                    for cand in list(candidates):
                        if verify_mp4_url(cand, page_url):
                            return MediaSource(
                                url=cand,
                                kind="direct",
                                content_type="video/mp4",
                                score=200,
                                source="tiktok",
                                referer=page_url
                            )
                        else:
                            if cand in candidates:
                                candidates.remove(cand)

                    # 檢查 DOM 是否跳出 Captcha 或登入彈窗
                    dom_text = await page.evaluate("() => document.body.innerText || ''")
                    if "puzzle" in dom_text.lower() or "drag the slider" in dom_text.lower():
                        has_captcha = True
                    if "登入以開始觀看" in dom_text or "Log in to watch" in dom_text:
                        has_login_gate = True

                    # 嘗試觸發播放器點擊
                    try:
                        play_btn = await page.query_selector("video, [class*='player'], [data-e2e*='play'], button[class*='play']")
                        if play_btn:
                            await play_btn.click()
                    except Exception:
                        pass

                    await page.wait_for_timeout(1000)

                # 若最後一輪檢驗
                for cand in candidates:
                    if verify_mp4_url(cand, page_url):
                        return MediaSource(
                            url=cand,
                            kind="direct",
                            content_type="video/mp4",
                            score=200,
                            source="tiktok",
                            referer=page_url
                        )

            finally:
                await browser.close()

        if has_captcha or has_login_gate:
            raise RuntimeError("TikTok 短劇觸發登入或拼圖驗證限制 (Captcha)。請至「系統設定」保存登入憑證 (auth_tiktok.json)，或直接在下載頁面貼上 Chrome DevTools 抓取的 video/mp4 URL")

        return None

    async def interactive_sniff(self, page_url: str, timeout: int = 90) -> Optional[MediaSource]:
        """Launch desktop browser (headless=False) to sniff video stream upon user puzzle pass/play."""
        from playwright.async_api import async_playwright
        import requests
        from urllib.parse import quote

        auth_file = Path("data/auth_tiktok.json")
        detected_url = None

        def verify_cand(u: str) -> bool:
            if any(k in u.lower() for k in ["playback", "ttwstatic", "login_static", "captcha", "thumb", "avatar"]):
                return False
            try:
                headers = {
                    "User-Agent": UA,
                    "Referer": quote(page_url, safe=":/%?&=#@+,"),
                    "Range": "bytes=0-1023",
                    "Accept": "video/avc,video/mp4,video/*;q=0.9,*/*;q=0.8",
                    "Accept-Encoding": "identity"
                }
                with requests.get(u, headers=headers, stream=True, timeout=5, allow_redirects=True) as resp:
                    if resp.status_code not in (200, 206): return False
                    cr = resp.headers.get("Content-Range", "")
                    cl = resp.headers.get("Content-Length", "")
                    total = 0
                    if cr and "/" in cr:
                        t_str = cr.split("/")[-1]
                        if t_str.isdigit(): total = int(t_str)
                    elif cl and cl.isdigit():
                        total = int(cl)
                    if 0 < total < 1024 * 1024: return False
                    sample = resp.raw.read(64)
                    return b"ftyp" in sample
            except Exception:
                return False

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
            )
            try:
                ctx_args = {
                    "user_agent": UA,
                    "locale": "zh-TW",
                    "viewport": {"width": 1280, "height": 850}
                }
                if auth_file.exists():
                    ctx_args["storage_state"] = str(auth_file)
                context = await browser.new_context(**ctx_args)
                page = await context.new_page()

                try:
                    from playwright_stealth import Stealth
                    await Stealth().apply_stealth_async(page)
                except Exception:
                    pass

                async def on_request(request):
                    nonlocal detected_url
                    if detected_url: return
                    u = request.url
                    if (request.resource_type == "media" or ".mp4" in u or "video" in u or "tiktokcdn.com" in u):
                        if verify_cand(u):
                            detected_url = u

                page.on("request", on_request)
                await page.goto(page_url, wait_until="domcontentloaded", timeout=timeout * 1000)

                for _ in range(timeout):
                    if detected_url:
                        try:
                            state = await context.storage_state()
                            auth_file.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
                        except Exception:
                            pass
                        break
                    await asyncio.sleep(1)

                if detected_url:
                    return MediaSource(
                        url=detected_url,
                        kind="direct",
                        content_type="video/mp4",
                        score=250,
                        source="tiktok_interactive",
                        referer=page_url
                    )
            finally:
                try:
                    await browser.close()
                except Exception:
                    pass

        return None

    def fetch_catalog(self, offset: int = 0, limit: int = 24, force_refresh: bool = False) -> Dict[str, Any]:
        """Fetch shortdrama catalog from TikTok with local caching and pagination."""
        cache_file = Path("data/tiktok_catalog_cache.json")
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        all_items = []
        if not force_refresh and cache_file.exists():
            try:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                if isinstance(data, list) and len(data) >= 40:
                    all_items = data
            except Exception:
                pass

        if not all_items or force_refresh:
            all_items = asyncio.run(self._refresh_catalog_async(cache_file))

        total = len(all_items)
        sliced = all_items[offset : offset + limit] if limit > 0 else all_items[offset:]
        return {
            "items": sliced,
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": (offset + len(sliced)) < total
        }

    async def _refresh_catalog_async(self, cache_file: Path) -> List[Dict[str, Any]]:
        from playwright.async_api import async_playwright
        drama_map = {}

        def format_count(n):
            try:
                num = int(n)
                if num >= 1_000_000:
                    return f"{num / 1_000_000:.1f}M"
                elif num >= 1_000:
                    return f"{num / 1_000:.1f}K"
                return str(num)
            except Exception:
                return str(n)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                auth_file = Path("data/auth_tiktok.json")
                ctx_args = {
                    "user_agent": UA,
                    "locale": "zh-TW"
                }
                if auth_file.exists():
                    ctx_args["storage_state"] = str(auth_file)
                context = await browser.new_context(**ctx_args)
                page = await context.new_page()

                async def on_resp(resp):
                    if "api/drama/theme/drama_list" in resp.url:
                        try:
                            j = await resp.json()
                            if "dramaList" in j and j["dramaList"]:
                                for d in j["dramaList"]:
                                    did = str(d.get("dramaID", ""))
                                    if did and did not in drama_map:
                                        drama_map[did] = d
                        except Exception:
                            pass

                page.on("response", on_resp)
                await page.goto("https://www.tiktok.com/shortdrama", wait_until="domcontentloaded", timeout=40000)

                # Wait for initial dramas
                for _ in range(12):
                    if drama_map:
                        break
                    await asyncio.sleep(0.5)

                # Scroll down 6 times with 3000px step to trigger TikTok pagination API
                for _ in range(6):
                    await page.evaluate("window.scrollBy(0, 3000)")
                    await asyncio.sleep(1.5)

            finally:
                await browser.close()

        results = []
        for did, d in drama_map.items():
            name = d.get("dramaName", "")
            watched = d.get("numWatched", 0)
            eps = int(d.get("numVideos", 0))
            covers = d.get("cover", {}).get("urlList", [])
            cover = covers[0] if covers else ""
            themes = [t.get("tagVal") for t in d.get("themes", []) if t.get("tagVal")]

            results.append({
                "drama_id": did,
                "title": name,
                "cover_url": cover,
                "num_videos": eps,
                "num_watched": watched,
                "watched_str": format_count(watched),
                "themes": themes,
                "page_url": f"https://www.tiktok.com/shortdrama/episode/{did}/1"
            })

        if results:
            cache_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

        return results

