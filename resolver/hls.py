from __future__ import annotations
import re
import requests
from dataclasses import dataclass, asdict
from urllib.parse import urljoin

@dataclass
class HLSVariant:
    url: str
    bandwidth: int = 0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    codecs: str = ""

    @property
    def quality(self):
        return f"{self.height}p" if self.height else "unknown"

    def score(self):
        return (self.height or 0) * 1000000 + self.bandwidth * 10 + int(self.fps * 100)

    def to_dict(self):
        return asdict(self) | {"quality": self.quality, "score": self.score()}

@dataclass
class HLSInfo:
    url: str
    variants: list[HLSVariant]
    is_master: bool
    media: bool

    def to_dict(self):
        return {
            "url": self.url,
            "is_master": self.is_master,
            "media": self.media,
            "variants": [v.to_dict() for v in self.variants],
        }

def inspect_hls(url, headers=None):
    h = {"User-Agent":"Mozilla/5.0"}
    if headers: h.update(headers)
    r = requests.get(url, headers=h, timeout=30)
    r.raise_for_status()
    text = r.text
    variants = []
    pending = None
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    for line in lines:
        if line.startswith("#EXT-X-STREAM-INF:"):
            pending = _attrs(line.split(":",1)[1])
        elif pending and not line.startswith("#"):
            uri = urljoin(url, line)
            res = pending.get("RESOLUTION","0x0").split("x")
            w,hg = (int(res[0]), int(res[1])) if len(res)==2 and res[0].isdigit() and res[1].isdigit() else (0,0)
            variants.append(HLSVariant(
                uri,
                int(float(pending.get("BANDWIDTH","0") or 0)),
                w,hg,
                float(pending.get("FRAME-RATE","0") or 0),
                pending.get("CODECS","")))
            pending = None
    return HLSInfo(url, variants, bool(variants), not bool(variants))

def _attrs(s):
    out={}
    for k,v in re.findall(r'([A-Z0-9-]+)=("[^"]*"|[^,]*)',s):
        out[k]=v.strip('"')
    return out
