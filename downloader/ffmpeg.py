from pathlib import Path
import shutil
import subprocess
from resolver.hls import inspect_hls

def ffmpeg_available():
    return shutil.which("ffmpeg") is not None

def download_hls(url, output, quality="best", progress_cb=None):
    if not ffmpeg_available():
        raise RuntimeError("找不到 ffmpeg，macOS 請先執行: brew install ffmpeg")
    info=inspect_hls(url)
    chosen=url
    if info.variants:
        variants=sorted(info.variants, key=lambda x:x.score(), reverse=True)
        if quality != "best":
            m=quality.lower().replace("p","")
            if m.isdigit():
                exact=[v for v in variants if v.height==int(m)]
                if exact: chosen=exact[0].url
                else: chosen=variants[0].url
            else: chosen=variants[0].url
        else:
            chosen=variants[0].url
    output=Path(output); output.parent.mkdir(parents=True, exist_ok=True)
    tmp=output.with_name(f"{output.stem}.part{output.suffix}")
    headers = "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36\r\nReferer: https://www.flextv.cc/\r\n"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-headers", headers,
        "-i", chosen,
        "-c", "copy",
        "-f", "mp4",
        "-movflags", "+faststart",
        "-progress", "pipe:1",
        str(tmp)
    ]
    if progress_cb: progress_cb(5)

    proc = None
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # Parse progress line by line
        last_pct = 5.0
        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break
            if "out_time_ms=" in line:
                try:
                    ms_val = int(line.split("out_time_ms=")[-1].strip())
                    secs = ms_val / 1000000.0
                    # Estimate based on typical 60s - 120s short drama episode
                    est_pct = min(95.0, 5.0 + (secs / 70.0) * 85.0)
                    if est_pct - last_pct >= 2.0:
                        last_pct = est_pct
                        if progress_cb: progress_cb(round(est_pct, 1))
                except Exception:
                    pass
            elif "progress=end" in line:
                break

        ret = proc.wait(timeout=30)
        if ret != 0:
            err = proc.stderr.read().strip() if proc.stderr else "ffmpeg 下載失敗"
            if tmp.exists(): tmp.unlink()
            raise RuntimeError(err or "ffmpeg 下載失敗")

        tmp.replace(output)
        if progress_cb: progress_cb(100)
        return str(output)
    except Exception:
        if proc and proc.poll() is None:
            proc.kill()
            proc.wait()
        if tmp.exists(): tmp.unlink()
        raise
    finally:
        if proc and proc.stdout: proc.stdout.close()
        if proc and proc.stderr: proc.stderr.close()
