import requests
from core.config import settings
from providers.base import Provider

class DramaBosProvider(Provider):
    name = "dramabos"

    def __init__(self):
        self.base = settings.dramabos_api_url.rstrip("/")
        self.key = settings.dramabos_api_key
        self.enabled = bool(self.base and self.key)

    def can_handle(self, url):
        return "dramabos" in url.lower()

    def _get(self, path, params=None):
        if not self.enabled:
            raise RuntimeError("DramaBos API 尚未設定")
        r = requests.get(
            self.base + "/" + path.lstrip("/"),
            params=params,
            headers={"Authorization": f"Bearer {self.key}", "Accept": "application/json"},
            timeout=30)
        r.raise_for_status()
        return r.json()

    def search(self, keyword):
        return self._get("/search", {"q": keyword})
