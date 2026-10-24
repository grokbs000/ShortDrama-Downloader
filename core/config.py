import json
from dataclasses import dataclass
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]
SETTINGS_FILE = ROOT / "data" / "settings.json"

@dataclass
class Settings:
    host: str = os.getenv("SHORTDRAMA_HOST", "127.0.0.1")
    port: int = int(os.getenv("SHORTDRAMA_PORT", "8765"))
    download_dir: Path = Path(os.getenv("SHORTDRAMA_DOWNLOAD_DIR", str(ROOT / "downloads"))).expanduser()
    db_path: Path = Path(os.getenv("SHORTDRAMA_DB", str(ROOT / "data" / "shortdrama.db"))).expanduser()
    dramabos_api_url: str = os.getenv("DRAMABOS_API_URL", "")
    dramabos_api_key: str = os.getenv("DRAMABOS_API_KEY", "")
    crawler_delay_min: float = float(os.getenv("SHORTDRAMA_CRAWLER_DELAY_MIN", "0.8"))
    crawler_delay_max: float = float(os.getenv("SHORTDRAMA_CRAWLER_DELAY_MAX", "2.0"))
    concurrency: int = int(os.getenv("SHORTDRAMA_CONCURRENCY", "3"))

    def load_persisted(self):
        if SETTINGS_FILE.exists():
            try:
                data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                if "download_dir" in data and data["download_dir"]:
                    p = Path(data["download_dir"]).expanduser().resolve()
                    self.download_dir = p
                    self.download_dir.mkdir(parents=True, exist_ok=True)
                if "crawler_delay_min" in data:
                    self.crawler_delay_min = max(0.1, float(data["crawler_delay_min"]))
                if "crawler_delay_max" in data:
                    self.crawler_delay_max = max(self.crawler_delay_min, float(data["crawler_delay_max"]))
                if "concurrency" in data:
                    self.concurrency = max(1, min(10, int(data["concurrency"])))
            except Exception:
                pass

    def save_settings(self, download_dir: str = None, crawler_delay_min: float = None, crawler_delay_max: float = None, concurrency: int = None):
        if download_dir:
            p = Path(download_dir).expanduser().resolve()
            p.mkdir(parents=True, exist_ok=True)
            self.download_dir = p
        if crawler_delay_min is not None:
            self.crawler_delay_min = max(0.1, float(crawler_delay_min))
        if crawler_delay_max is not None:
            self.crawler_delay_max = max(self.crawler_delay_min, float(crawler_delay_max))
        if concurrency is not None:
            self.concurrency = max(1, min(10, int(concurrency)))
        
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "download_dir": str(self.download_dir),
            "crawler_delay_min": self.crawler_delay_min,
            "crawler_delay_max": self.crawler_delay_max,
            "concurrency": self.concurrency
        }
        SETTINGS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

settings = Settings()
settings.load_persisted()
settings.download_dir.mkdir(parents=True, exist_ok=True)
settings.db_path.parent.mkdir(parents=True, exist_ok=True)
