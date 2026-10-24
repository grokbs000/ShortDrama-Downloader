from dataclasses import dataclass, asdict
from typing import Optional

@dataclass
class MediaSource:
    url: str
    kind: str
    content_type: str = ""
    quality: str = ""
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    bitrate: Optional[int] = None
    size: Optional[int] = None
    score: int = 0
    source: str = ""
    referer: Optional[str] = None

    def to_dict(self):
        return asdict(self)

@dataclass
class DownloadTask:
    id: int
    url: str
    title: str
    episode: int
    quality: str
    status: str
    progress: float
    output: str = ""
    error: str = ""
