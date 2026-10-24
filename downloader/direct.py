from pathlib import Path
import requests
from tqdm import tqdm

import time
from urllib.parse import quote
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/154.0.0.0 Safari/537.36"

# Reusable HTTP session with connection pooling
_session = requests.Session()
_adapter = HTTPAdapter(pool_connections=10, pool_maxsize=20, max_retries=Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504]))
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)

def is_valid_mp4_header(data: bytes) -> bool:
    return bool(data) and b"ftyp" in data[:64]

def download_direct(url, output, referer=None, progress_cb=None):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".part")
    
    headers = {
        "User-Agent": UA,
        "Accept": "video/avc,video/mp4,video/*;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive"
    }
    if referer:
        try:
            headers["Referer"] = quote(referer, safe=":/%?&=#@+,")
        except Exception:
            pass

    existing_bytes = tmp.stat().st_size if tmp.exists() else 0
    if existing_bytes > 0:
        headers["Range"] = f"bytes={existing_bytes}-"

    with _session.get(url, headers=headers, stream=True, timeout=(15, 180), allow_redirects=True) as r:
        if r.status_code in (401, 403):
            raise RuntimeError(f"HTTP {r.status_code}: 來源需要授權、已過期或網站限制請求 (Signed URL 已失效)")
        if r.status_code == 416:  # Requested Range Not Satisfiable
            # Range was invalid, retry clean
            if tmp.exists(): tmp.unlink()
            existing_bytes = 0
            headers.pop("Range", None)
            r = _session.get(url, headers=headers, stream=True, timeout=(15, 180), allow_redirects=True)

        if r.status_code not in (200, 206):
            raise RuntimeError(f"HTTP {r.status_code}: 伺服器拒絕請求")

        ct = (r.headers.get("Content-Type") or "").lower()
        if "text/html" in ct or "application/json" in ct:
            raise RuntimeError("伺服器回傳 HTML/JSON，非影片串流")
        
        is_partial = (r.status_code == 206)
        content_len = int(r.headers.get("Content-Length", "0") or 0)
        total = existing_bytes + content_len if is_partial else content_len

        # 若已知大小且小於 500KB，直接拒絕 (排除 TikTok 193KB 音符 Logo 宣傳片)
        if 0 < total < 500 * 1024:
            raise RuntimeError(f"檔案大小過小 ({total} bytes)，非短劇正片 (疑似 TikTok 宣傳片/Logo)")

        mode = "ab" if is_partial else "wb"
        got = existing_bytes if is_partial else 0
        header_sample = b""
        if is_partial and tmp.exists() and existing_bytes >= 64:
            with open(tmp, "rb") as ef:
                header_sample = ef.read(64)

        last_progress_time = 0.0
        last_progress_val = 0.0

        try:
            with open(tmp, mode) as f, tqdm(total=total or None, initial=got, unit="B", unit_scale=True) as bar:
                for chunk in r.iter_content(1024 * 1024):
                    if not chunk: continue
                    if len(header_sample) < 64:
                        header_sample += chunk[:64 - len(header_sample)]
                    f.write(chunk)
                    got += len(chunk)
                    bar.update(len(chunk))
                    
                    if progress_cb and total:
                        pct = min(99.0, (got * 100.0) / total)
                        now = time.time()
                        if (pct - last_progress_val >= 1.0 or now - last_progress_time >= 0.4):
                            progress_cb(pct)
                            last_progress_val = pct
                            last_progress_time = now

            if got < 500 * 1024:
                raise RuntimeError(f"實際下載大小僅 {got} bytes，非短劇正片 (疑似 TikTok Logo 動畫)")

            if not is_valid_mp4_header(header_sample):
                raise RuntimeError("檔案標頭未檢測到標準 MP4 ftyp 簽名")

            tmp.replace(output)
        except Exception:
            if not is_partial and tmp.exists():
                tmp.unlink()
            raise

    if progress_cb: progress_cb(100)
    return str(output)
