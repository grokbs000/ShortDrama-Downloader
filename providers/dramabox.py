import re
import json
import asyncio
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
import requests
from bs4 import BeautifulSoup
import urllib.parse

from providers.base import Provider
from core.models import MediaSource
from core.crawler import dynamic_delay_sync

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

@dataclass
class DramaBoxEpisode:
    episode_no: int
    title: str
    is_locked: bool
    cover_url: str
    page_url: str
    video_url: str = ""
    m3u8_url: str = ""

    def to_dict(self):
        return {
            "episode_no": self.episode_no,
            "title": self.title,
            "is_locked": self.is_locked,
            "cover_url": self.cover_url,
            "page_url": self.page_url,
            "video_url": self.video_url,
            "m3u8_url": self.m3u8_url,
        }

@dataclass
class DramaBoxDrama:
    drama_id: str
    title: str
    cover_url: str
    intro: str
    total_episodes: int
    episodes: List[DramaBoxEpisode]
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

class DramaBoxProvider(Provider):
    name = "dramabox"

    def can_handle(self, url: str) -> bool:
        if not url: return False
        u = url.lower()
        return "dramaboxdb.com" in u or "dramabox.com" in u

    def extract_book_id(self, url: str) -> str:
        # e.g. /movie/42000021919/play or /movie/42000021919/love-game
        m = re.search(r"/movie/(\d+)", url)
        if m: return m.group(1)
        m2 = re.search(r"/detail/(\d+)", url)
        if m2: return m2.group(1)
        return ""

    def fetch_catalog(self, offset: int = 0, limit: int = 24, force_refresh: bool = False) -> Dict[str, Any]:
        """Fetch DramaBox catalog from homepage with caching and pagination."""
        cache_file = Path("data/dramabox_catalog_cache.json")
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
        headers = {"User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8"}
        url = "https://www.dramaboxdb.com"
        results = []
        seen_ids = set()

        try:
            r = requests.get(url, headers=headers, timeout=(10, 30))
            if r.status_code != 200:
                return results

            soup = BeautifulSoup(r.text, "html.parser")
            tag = soup.find("script", id="__NEXT_DATA__")
            if not tag or not tag.string:
                return results

            data = json.loads(tag.string)
            page_props = data.get("props", {}).get("pageProps", {})

            # 1. bigList (Featured dramas)
            big_list = page_props.get("bigList", [])
            for item in big_list:
                b_id = str(item.get("bookId") or "")
                if not b_id or b_id in seen_ids: continue
                seen_ids.add(b_id)
                results.append(self._format_catalog_item(item))

            # 2. smallData (Category collections)
            small_data = page_props.get("smallData", [])
            for section in small_data:
                items = section.get("items", [])
                for it in items:
                    b_id = str(it.get("bookId") or "")
                    if not b_id or b_id in seen_ids: continue
                    seen_ids.add(b_id)
                    results.append(self._format_catalog_item(it))

        except Exception as e:
            print(f"[DramaBox] Catalog scrape error: {e}")

        return results

    def _format_catalog_item(self, it: Dict[str, Any]) -> Dict[str, Any]:
        b_id = str(it.get("bookId", ""))
        title = (it.get("bookName") or "DramaBox短劇").strip()
        cover = it.get("cover") or ""
        chapter_count = int(it.get("chapterCount") or 0)
        intro = (it.get("introduction") or "").strip()
        tags = it.get("tags") or it.get("labels") or []

        return {
            "id": b_id,
            "drama_id": b_id,
            "title": title,
            "cover_url": cover,
            "episodes_count": chapter_count,
            "intro": intro,
            "tags": tags if isinstance(tags, list) else [str(tags)],
            "detail_url": f"https://www.dramaboxdb.com/movie/{b_id}/play",
            "provider": "dramabox"
        }

    def get_drama(self, url: str) -> DramaBoxDrama:
        book_id = self.extract_book_id(url)
        if not book_id:
            raise ValueError(f"無法從網址提取 DramaBox 短劇 ID: {url}")

        play_url = f"https://www.dramaboxdb.com/movie/{book_id}/play"
        headers = {"User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8"}
        
        r = requests.get(play_url, headers=headers, timeout=(10, 30))
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        tag = soup.find("script", id="__NEXT_DATA__")
        if not tag or not tag.string:
            raise RuntimeError("無法獲取 DramaBox 頁面資料結構")

        data = json.loads(tag.string)
        page_props = data.get("props", {}).get("pageProps", {})
        book_info = page_props.get("bookInfo", {})
        chapter_list = page_props.get("chapterList", [])

        title = book_info.get("bookName") or "DramaBox 短劇"
        cover_url = book_info.get("cover") or ""
        intro = book_info.get("introduction") or ""

        episodes: List[DramaBoxEpisode] = []
        for ch in chapter_list:
            ep_idx = int(ch.get("index", 0)) + 1
            ep_name = ch.get("name") or f"第 {ep_idx} 集"
            unlock = bool(ch.get("unlock", True))
            ep_cover = ch.get("cover") or cover_url
            mp4_url = ch.get("mp4") or ""
            m3u8_url = ch.get("m3u8Url") or ""

            ep_page_url = f"https://www.dramaboxdb.com/movie/{book_id}/play?ep={ep_idx}"
            episodes.append(DramaBoxEpisode(
                episode_no=ep_idx,
                title=ep_name,
                is_locked=not unlock,
                cover_url=ep_cover,
                page_url=ep_page_url,
                video_url=mp4_url,
                m3u8_url=m3u8_url
            ))

        return DramaBoxDrama(
            drama_id=book_id,
            title=title,
            cover_url=cover_url,
            intro=intro,
            total_episodes=len(episodes),
            episodes=episodes,
            canonical_url=play_url
        )

    async def resolve_video_url(self, page_url: str, timeout: int = 30) -> Optional[MediaSource]:
        """Resolve direct video stream for DramaBox episode."""
        try:
            m = re.search(r"[?&]ep=(\d+)", page_url)
            target_ep = int(m.group(1)) if m else 1
            
            drama = self.get_drama(page_url)
            for ep in drama.episodes:
                if ep.episode_no == target_ep:
                    if ep.video_url:
                        return MediaSource(
                            url=ep.video_url,
                            kind="direct",
                            content_type="video/mp4",
                            score=180,
                            source="dramabox",
                            referer="https://www.dramaboxdb.com/"
                        )
                    elif ep.m3u8_url:
                        return MediaSource(
                            url=ep.m3u8_url,
                            kind="hls",
                            content_type="application/vnd.apple.mpegurl",
                            score=170,
                            source="dramabox",
                            referer="https://www.dramaboxdb.com/"
                        )
        except Exception as e:
            print(f"[DramaBox] resolve error: {e}")

        return None
