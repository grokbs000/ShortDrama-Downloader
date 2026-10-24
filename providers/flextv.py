import re
import json
import asyncio
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor
import requests
from bs4 import BeautifulSoup
import urllib.parse

from providers.base import Provider
from core.models import MediaSource
from core.crawler import dynamic_delay_sync, dynamic_delay_async

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

@dataclass
class FlexTVEpisode:
    episode_no: int
    title: str
    is_locked: bool
    cover_url: str
    page_url: str

    def to_dict(self):
        return {
            "episode_no": self.episode_no,
            "title": self.title,
            "is_locked": self.is_locked,
            "cover_url": self.cover_url,
            "page_url": self.page_url,
        }

@dataclass
class FlexTVDrama:
    drama_id: str
    title: str
    cover_url: str
    intro: str
    total_episodes: int
    episodes: List[FlexTVEpisode]
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

class FlexTVProvider(Provider):
    name = "flextv"

    CATEGORIES = [
        "/tc/dramas/all-dramas",
        "/tc/dramas/%E5%A5%87%E5%B9%BB-91deg4enpg",
        "/tc/dramas/%E5%AE%B6%E5%BA%AD-vg08d9omy3",
        "/tc/dramas/%E6%87%B8%E7%96%91-d9yend8ox6",
        "/tc/dramas/%E6%88%90%E9%95%B7-pzjmyx7e6g",
        "/tc/dramas/%E6%AD%A6%E4%BF%A0-36lew0omgd",
        "/tc/dramas/%E7%8E%84%E5%B9%BB-0ngmjpxmk6",
        "/tc/dramas/%E7%A7%91%E5%B9%BB-5wke7jgedr",
        "/tc/dramas/%E8%81%B7%E5%A0%B4-3p9mvynmk1",
        "/tc/dramas/%E8%A8%80%E6%83%85-od4ekk2e7n",
        "/tc/dramas/%E9%83%BD%E5%B8%82-n9le3orez3",
        "/tc/dramas/%E9%9D%92%E6%98%A5-5168rv3egy"
    ]

    def can_handle(self, url: str) -> bool:
        if not url: return False
        u = url.lower()
        return "flextv.cc" in u

    def extract_slug_and_episode(self, url: str):
        # Match pattern: /tc/episodes/episode-(\d+)-(.*)
        m_ep = re.search(r"/tc/episodes/episode-(\d+)-([^/?#]+)", url)
        if m_ep:
            ep_no = int(m_ep.group(1))
            slug = m_ep.group(2)
            return slug, ep_no

        # Match pattern: /tc/movie/([^/?#]+)
        m_mov = re.search(r"/tc/movie/([^/?#]+)", url)
        if m_mov:
            slug = m_mov.group(1)
            return slug, 1

        return "", 1

    def fetch_catalog(self, offset: int = 0, limit: int = 24, force_refresh: bool = False) -> Dict[str, Any]:
        """Fetch Flex TV catalog with caching and pagination."""
        cache_file = Path("data/flextv_catalog_cache.json")
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        all_items = []
        if not force_refresh and cache_file.exists():
            try:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                if isinstance(data, list) and len(data) >= 20:
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
        headers = {"User-Agent": UA, "Referer": "https://www.flextv.cc/"}
        dramas = {}

        def fetch_cat(cat_path):
            url = f"https://www.flextv.cc{cat_path}"
            try:
                r = requests.get(url, headers=headers, timeout=12)
                if r.status_code == 200:
                    return r.text
            except Exception:
                pass
            return ""

        with ThreadPoolExecutor(max_workers=6) as pool:
            htmls = list(pool.map(fetch_cat, self.CATEGORIES))

        for html in htmls:
            if not html: continue
            soup = BeautifulSoup(html, "html.parser")
            cards = soup.select("article.tag-drama-card")
            for c in cards:
                a_cover = c.select_one("a.tag-drama-card__cover")
                if not a_cover or not a_cover.get("href"):
                    continue
                href = a_cover["href"]
                slug = href.split("/")[-1]
                if not slug: continue

                title_el = c.select_one("h3.tag-drama-card__title a") or a_cover
                title = title_el.text.strip() if title_el else urllib.parse.unquote(slug)
                img_el = c.select_one("img")
                cover = (img_el.get("src") or img_el.get("data-src") or "") if img_el else ""
                tag_el = c.select_one(".tag-drama-card__tag, .tag, [class*=\"tag\"]")
                tag = tag_el.text.strip() if tag_el else "熱門"

                if slug not in dramas:
                    dramas[slug] = {
                        "id": slug,
                        "title": title,
                        "cover_url": cover,
                        "canonical_url": f"https://www.flextv.cc{href}",
                        "category": tag or "熱門",
                        "views": "HD",
                        "episodes_count": 0,
                        "source": "flextv"
                    }

        return list(dramas.values())

    def get_drama(self, url: str) -> FlexTVDrama:
        """Parse drama details: title, total episodes, episode list."""
        dynamic_delay_sync()
        slug, current_ep = self.extract_slug_and_episode(url)
        headers = {"User-Agent": UA, "Referer": "https://www.flextv.cc/"}
        movie_url = f"https://www.flextv.cc/tc/movie/{slug}" if slug else url

        r = requests.get(movie_url, headers=headers, timeout=15)
        html = r.text if r.status_code == 200 else ""
        soup = BeautifulSoup(html, "html.parser")

        # Parse title
        h1 = soup.select_one("h1")
        title_raw = h1.text.strip() if h1 else ""
        title = re.sub(r"^在線觀看\s*|\s*全集免費高清.*|\s*-\s*FlexTV.*", "", title_raw).strip()
        if not title:
            # Fallback to page title or unquoted slug
            p_title = soup.select_one("title")
            if p_title:
                title = re.sub(r"短劇與電影線上免費觀看.*|全集線上免費看.*|-.*", "", p_title.text.strip()).strip()
        if not title and slug:
            title = urllib.parse.unquote(slug).rsplit("-", 1)[0]
        if not title:
            title = "FlexTV ShortDrama"

        # Cover
        cover_img = soup.select_one(".series-info-cover img, .cover img, img")
        cover_url = cover_img.get("src", "") if cover_img else ""

        # Intro
        desc_el = soup.select_one(".series-info-desc, .desc, meta[name='description']")
        intro = ""
        if desc_el:
            intro = desc_el.get("content", "") if desc_el.name == "meta" else desc_el.text.strip()

        # Total episode count
        eps_m = re.search(r"(\d+)\s*集數", html) or re.search(r"全劇共\s*(\d+)\s*集", html)
        total_eps = int(eps_m.group(1)) if eps_m else 1

        # Check unlocked / episode elements if present in DOM
        ep_items_count = len(soup.select("a.episode-item, .episode-item"))
        if ep_items_count > total_eps:
            total_eps = ep_items_count

        episodes = []
        for ep_i in range(1, total_eps + 1):
            ep_url = f"https://www.flextv.cc/tc/episodes/episode-{ep_i}-{slug}" if slug else url
            episodes.append(FlexTVEpisode(
                episode_no=ep_i,
                title=f"{title} - Episode {ep_i}",
                is_locked=False,
                cover_url=cover_url,
                page_url=ep_url
            ))

        return FlexTVDrama(
            drama_id=slug or "flextv_drama",
            title=title,
            cover_url=cover_url,
            intro=intro,
            total_episodes=len(episodes),
            episodes=episodes,
            canonical_url=movie_url
        )

    async def resolve_video_url(self, page_url: str, timeout: int = 25) -> Optional[MediaSource]:
        """Resolve signed HLS m3u8 stream from Flex TV page with lightning HTTP and Playwright fallback."""
        headers = {"User-Agent": UA, "Referer": "https://www.flextv.cc/"}

        # Step 1: Lightning HTTP SSR Check
        try:
            await dynamic_delay_async()
            r = await asyncio.to_thread(requests.get, page_url, headers=headers, timeout=12)
            if r.status_code == 200:
                m3u8s = re.findall(r'https://resources-sgp-auth\.flextv\.cc[^\"]+abr\.m3u8\?auth_key=[^\"]+', r.text)
                if not m3u8s:
                    # Generic m3u8 regex
                    m3u8s = re.findall(r'https?://[^\s\"\'<>]+\.m3u8[^\s\"\'<>]*', r.text)
                if m3u8s:
                    return MediaSource(
                        url=m3u8s[0],
                        kind="hls",
                        source="flextv",
                        quality="best",
                        referer="https://www.flextv.cc/"
                    )
        except Exception:
            pass

        # Step 2: Playwright Sniffing Fallback
        try:
            from playwright.async_api import async_playwright
            captured_m3u8 = None

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    page = await browser.new_page(user_agent=UA)
                    async def on_resp(resp):
                        nonlocal captured_m3u8
                        if captured_m3u8: return
                        u = resp.url
                        if ".m3u8" in u or "resources-sgp-auth" in u:
                            captured_m3u8 = u

                    page.on("response", on_resp)
                    await page.goto(page_url, wait_until="domcontentloaded", timeout=timeout * 1000)

                    for _ in range(10):
                        if captured_m3u8: break
                        await asyncio.sleep(0.5)

                finally:
                    await browser.close()

            if captured_m3u8:
                return MediaSource(
                    url=captured_m3u8,
                    kind="hls",
                    source="flextv",
                    quality="best",
                    referer="https://www.flextv.cc/"
                )
        except Exception:
            pass

        return None
