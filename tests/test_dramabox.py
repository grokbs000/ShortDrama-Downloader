import unittest
from fastapi.testclient import TestClient
from app import app
from providers.dramabox import DramaBoxProvider
from providers.netshort import NetShortProvider

class TestNewProviders(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.dramabox = DramaBoxProvider()
        self.netshort = NetShortProvider()

    def test_dramabox_can_handle(self):
        self.assertTrue(self.dramabox.can_handle("https://www.dramaboxdb.com/movie/42000021919/play"))
        self.assertTrue(self.dramabox.can_handle("https://dramabox.com/movie/123"))
        self.assertFalse(self.dramabox.can_handle("https://www.tiktok.com/@test"))

    def test_dramabox_catalog_api(self):
        res = self.client.get("/api/dramabox/catalog?offset=0&limit=5")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("ok"))
        self.assertIn("items", data)
        self.assertIn("total", data)

    def test_netshort_catalog_api(self):
        res = self.client.get("/api/netshort/catalog?offset=0&limit=5")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("ok"))
        self.assertIn("items", data)
        self.assertIn("total", data)

    def test_dramabox_drama_info_api(self):
        test_url = "https://www.dramaboxdb.com/movie/42000021919/play"
        res = self.client.post("/api/drama/info", json={"url": test_url})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("provider"), "dramabox")
        drama = data.get("drama", {})
        self.assertIn("title", drama)
        self.assertGreater(len(drama.get("episodes", [])), 0)

if __name__ == "__main__":
    unittest.main()
