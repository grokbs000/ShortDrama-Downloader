from __future__ import annotations
import asyncio
import re
import requests
from dataclasses import dataclass, asdict
from urllib.parse import urlparse
from core.models import MediaSource

VIDEO_EXT = (".mp4",".webm",".mov",".mkv")
HLS_EXT = (".m3u8",)
DASH_EXT = (".mpd",)
NEGATIVE = ("thumb","thumbnail","cover","avatar","logo","poster","preview","trailer","teaser","ad.","ads.","banner")

def score_url(url, content_type="", size=None):
    u = url.lower()
    s = 0
    if "video/" in content_type: s += 80
    if u.endswith(".mp4") or ".mp4?" in u or "mime_type=video_mp4" in u: s += 50
    if u.endswith(".m3u8") or ".m3u8?" in u or "mpegurl" in content_type: s += 60
    if any(x in u for x in NEGATIVE): s -= 80
    if size and size > 5*1024*1024: s += 30
    elif size and size > 1024*1024: s += 15
    return s

def inspect_url(url, referer=None):
    try:
        r = requests.get(url, headers=_headers(referer), stream=True, timeout=(10,30), allow_redirects=True)
        ct = r.headers.get("Content-Type","").split(";")[0].lower()
        size = int(r.headers.get("Content-Length","0") or 0) or None
        final = r.url
        final_lower = final.lower()
        if "mpegurl" in ct or final_lower.split("?")[0].endswith(HLS_EXT):
            kind = "hls"
        elif "dash" in ct or final_lower.split("?")[0].endswith(DASH_EXT):
            kind = "dash"
        elif ct.startswith("video/") or final_lower.split("?")[0].endswith(VIDEO_EXT) or "mime_type=video_mp4" in final_lower:
            kind = "direct"
        else:
            kind = "unknown"
        r.close()
        return MediaSource(final, kind, ct, size=size, score=score_url(final,ct,size), source="inspect", referer=referer)
    except requests.RequestException:
        return None

def _headers(referer):
    from urllib.parse import quote
    h = {"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/154.0.0.0 Safari/537.36"}
    if referer:
        try:
            h["Referer"] = quote(referer, safe=":/%?&=#@+,")
        except Exception:
            pass
    return h

async def detect_page(page_url, timeout=60):
    from playwright.async_api import async_playwright
    found = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page(user_agent=_headers(None)["User-Agent"])
            async def on_response(resp):
                try:
                    ct = (resp.headers.get("content-type") or "").split(";")[0].lower()
                    u = resp.url
                    lu = u.lower()
                    if ct.startswith("video/") or "mpegurl" in ct or "dash" in ct or any(x in lu for x in (".mp4",".webm",".m3u8",".mpd","mime_type=video_mp4")):
                        if any(x in lu for x in NEGATIVE):
                            return
                        kind = "direct" if (ct.startswith("video/") or any(x in lu for x in VIDEO_EXT) or "mime_type=video_mp4" in lu) else ("hls" if (".m3u8" in lu or "mpegurl" in ct) else "dash")
                        found[u] = MediaSource(u, kind, ct, score=score_url(u, ct), source="playwright", referer=page_url)
                except Exception:
                    pass
            page.on("response", on_response)
            await page.goto(page_url, wait_until="domcontentloaded", timeout=timeout*1000)

            # Wait and inspect DOM or click play
            for _ in range(5):
                if found:
                    break
                try:
                    v_src = await page.evaluate("() => { const v = document.querySelector('video[src]'); return v ? v.src : null; }")
                    if v_src and "http" in v_src and not any(x in v_src for x in ["blob:", "thumb"]):
                        found[v_src] = MediaSource(v_src, "direct", "video/mp4", score=120, source="playwright_dom", referer=page_url)
                        break
                    btn = await page.query_selector("button, .play-btn, [class*='play']")
                    if btn: await btn.click()
                except Exception:
                    pass
                await asyncio.sleep(1)

            await asyncio.sleep(2)
        finally:
            await browser.close()
    return sorted(found.values(), key=lambda x: x.score, reverse=True)
