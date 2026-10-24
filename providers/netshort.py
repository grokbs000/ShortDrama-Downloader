import re
import json
import requests
from urllib.parse import urlparse, unquote
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from providers.base import Provider
from core.models import MediaSource

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

@dataclass
class NetShortEpisode:
    episode_id: str
    episode_no: int
    is_locked: bool
    cover_url: str
    page_url: str

    def to_dict(self):
        return {
            "episode_id": self.episode_id,
            "episode_no": self.episode_no,
            "is_locked": self.is_locked,
            "cover_url": self.cover_url,
            "page_url": self.page_url,
        }

@dataclass
class NetShortDrama:
    drama_id: str
    title: str
    cover_url: str
    intro: str
    total_episodes: int
    episodes: List[NetShortEpisode]
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

class NetShortProvider(Provider):
    name = "netshort"

    def can_handle(self, url: str) -> bool:
        if not url: return False
        return "netshort.com" in url.lower()

    def fetch_catalog(self, offset: int = 0, limit: int = 24, force_refresh: bool = False) -> Dict[str, Any]:
        """Fetch NetShort catalog with local caching and pagination."""
        from pathlib import Path
        cache_file = Path("data/netshort_catalog_cache.json")
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        all_items = []
        if not force_refresh and cache_file.exists():
            try:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                if isinstance(data, list) and len(data) >= 10:
                    all_items = data
            except Exception:
                pass

        if not all_items or force_refresh:
            all_items = self._scrape_catalog_sync()
            if all_items:
                try:
                    cache_file.write_text(json.dumps(all_items, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass

        total = len(all_items)
        sliced = all_items[offset : offset + limit] if limit > 0 else all_items[offset:]
        return {
            "items": sliced,
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": (offset + len(sliced)) < total
        }

    def _scrape_catalog_sync(self) -> List[Dict[str, Any]]:
        from bs4 import BeautifulSoup
        headers = {
            "User-Agent": UA,
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
            "Referer": "https://netshort.com/"
        }
        results = []
        seen = set()

        try:
            r = requests.get("https://netshort.com/zh", headers=headers, timeout=(10, 30))
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    m = re.search(r"/episode/([^/?#]+)-(\d{10,})", href)
                    if m:
                        b_id = m.group(2)
                        raw_title = unquote(m.group(1).split("-ep-")[0].strip())
                        if b_id not in seen:
                            seen.add(b_id)
                            img = a.find("img")
                            cover = (img.get("src") or img.get("data-src") or "") if img else ""
                            results.append({
                                "id": b_id,
                                "drama_id": b_id,
                                "title": raw_title,
                                "cover_url": cover,
                                "episodes_count": 0,
                                "intro": "",
                                "tags": ["熱門短劇"],
                                "detail_url": f"https://netshort.com{href}" if href.startswith("/") else href,
                                "provider": "netshort"
                            })
        except Exception as e:
            print(f"[NetShort] Catalog scrape error: {e}")

        return results

    def fetch_page_html(self, url: str) -> str:
        headers = {
            "User-Agent": UA,
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
            "Referer": "https://netshort.com/"
        }
        r = requests.get(url, headers=headers, timeout=(10, 30))
        r.raise_for_status()
        return r.text

    def parse_drama(self, url: str) -> NetShortDrama:
        path = unquote(urlparse(url).path)
        # Parse title and drama_id from path: /zh/episode/<name>-<id>[-ep-<no>]
        parsed_title = "ShortDrama"
        parsed_id = ""
        m = re.search(r"/episode/([^/?#]+)-(\d{10,})", path)
        if m:
            parsed_title = m.group(1).split("-ep-")[0].strip()
            parsed_id = m.group(2)

        # Build clean canonical base URL
        # e.g. https://netshort.com/zh/episode/{parsed_title}-{parsed_id}
        parsed_netloc = urlparse(url).netloc or "netshort.com"
        scheme = urlparse(url).scheme or "https"
        canonical_base = f"{scheme}://{parsed_netloc}/zh/episode/{parsed_title}-{parsed_id}"

        html = self.fetch_page_html(url)

        # Extract RSC chunks
        chunks = re.findall(r"self\.__next_f\.push\(\[1,\s*\"(.*?)\"\]\)", html)
        full_rsc = ""
        for c in chunks:
            try:
                full_rsc += c.encode("utf-8").decode("unicode_escape", errors="ignore")
            except Exception:
                full_rsc += c

        source_text = full_rsc if full_rsc else html

        # Look for shortPlayDetailVo
        cover_url = ""
        intro = ""

        # Cover
        m_cover = re.search(r"\"shortPlayCover\":\"(https?://[^\"]+)\"", source_text)
        if m_cover:
            cover_url = m_cover.group(1)

        # Intro
        m_intro = re.search(r"\"shotIntroduce\":\"(.*?)\"", source_text)
        if m_intro:
            intro = m_intro.group(1)

        # Extract episodes from videoEpisodeInfos
        episodes: List[NetShortEpisode] = []
        idx = source_text.find("\"videoEpisodeInfos\":")
        if idx != -1:
            sub = source_text[idx + len("\"videoEpisodeInfos\":"):]
            cnt = 0
            end = -1
            for i, ch in enumerate(sub):
                if ch == "[": cnt += 1
                elif ch == "]":
                    cnt -= 1
                    if cnt == 0:
                        end = i + 1
                        break
            if end != -1:
                try:
                    data = json.loads(sub[:end])
                    for item in data:
                        ep_no = int(item.get("episodeNo", 1))
                        ep_url = canonical_base if ep_no == 1 else f"{canonical_base}-ep-{ep_no}"
                        episodes.append(NetShortEpisode(
                            episode_id=str(item.get("episodeId", "")),
                            episode_no=ep_no,
                            is_locked=bool(item.get("isLock", False)),
                            cover_url=item.get("episodeCover", ""),
                            page_url=ep_url
                        ))
                except Exception:
                    pass

        # Sort episodes
        episodes.sort(key=lambda x: x.episode_no)

        return NetShortDrama(
            drama_id=parsed_id,
            title=parsed_title,
            cover_url=cover_url,
            intro=intro,
            total_episodes=len(episodes),
            episodes=episodes,
            canonical_url=canonical_base
        )

    def get_drama(self, url: str) -> NetShortDrama:
        return self.parse_drama(url)

    async def resolve_video_url(self, page_url: str, timeout: int = 30) -> Optional[MediaSource]:
        """Sniff actual video stream with Playwright in headless mode."""
        from playwright.async_api import async_playwright
        found_url = None
        found_ct = None

        from pathlib import Path
        auth_file = Path("data/auth_netshort.json")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                ctx_args = {"user_agent": UA, "locale": "zh-TW"}
                if auth_file.exists():
                    ctx_args["storage_state"] = str(auth_file)
                context = await browser.new_context(**ctx_args)
                page = await context.new_page()

                async def on_resp(resp):
                    nonlocal found_url, found_ct
                    if found_url: return
                    u = resp.url
                    ct = (resp.headers.get("content-type") or "").lower()
                    if ("video/mp4" in ct or "mime_type=video_mp4" in u) and not any(x in u.lower() for x in ["thumb", "preview", "trailer", "ad."]):
                        found_url = u
                        found_ct = ct or "video/mp4"

                page.on("response", on_resp)
                await page.goto(page_url, wait_until="domcontentloaded", timeout=timeout * 1000)

                for _ in range(8):
                    if found_url: break
                    v_src = await page.evaluate("() => { const v = document.querySelector('video[src]'); return v ? v.src : null; }")
                    if v_src and "http" in v_src and not any(x in v_src for x in ["blob:", "thumb"]):
                        found_url = v_src
                        found_ct = "video/mp4"
                        break

                    try:
                        btn = await page.query_selector("button, .play-btn, [class*='play']")
                        if btn: await btn.click()
                    except Exception:
                        pass

                    await page.wait_for_timeout(1000)

                if found_url:
                    return MediaSource(
                        url=found_url,
                        kind="direct",
                        content_type=found_ct or "video/mp4",
                        score=150,
                        source="netshort",
                        referer=page_url
                    )
            finally:
                await browser.close()
        return None
