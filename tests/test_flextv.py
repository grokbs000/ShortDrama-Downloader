import unittest
from fastapi.testclient import TestClient
from pathlib import Path

from app import app
from providers.flextv import FlexTVProvider

class TestFlexTV(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.provider = FlexTVProvider()

    def test_can_handle(self):
        self.assertTrue(self.provider.can_handle("https://www.flextv.cc/tc/dramas/all-dramas"))
        self.assertTrue(self.provider.can_handle("https://www.flextv.cc/tc/movie/test-movie-123"))
        self.assertTrue(self.provider.can_handle("https://www.flextv.cc/tc/episodes/episode-1-test-movie-123"))
        self.assertFalse(self.provider.can_handle("https://www.tiktok.com/shortdrama"))
        self.assertFalse(self.provider.can_handle("https://netshort.com/"))

    def test_extract_slug_and_episode(self):
        slug, ep = self.provider.extract_slug_and_episode("https://www.flextv.cc/tc/episodes/episode-5-my-drama-slug")
        self.assertEqual(slug, "my-drama-slug")
        self.assertEqual(ep, 5)

        slug2, ep2 = self.provider.extract_slug_and_episode("https://www.flextv.cc/tc/movie/my-drama-slug")
        self.assertEqual(slug2, "my-drama-slug")
        self.assertEqual(ep2, 1)

    def test_flextv_catalog_api(self):
        res = self.client.get("/api/flextv/catalog?offset=0&limit=6")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("ok"))
        self.assertIn("items", data)
        self.assertIn("total", data)
        self.assertGreater(data["total"], 0)
        self.assertLessEqual(len(data["items"]), 6)
        if data["items"]:
            first = data["items"][0]
            self.assertIn("id", first)
            self.assertIn("title", first)
            self.assertIn("cover_url", first)
            self.assertIn("canonical_url", first)

    def test_flextv_drama_info_api(self):
        # Use first drama from catalog
        cat_res = self.client.get("/api/flextv/catalog?offset=0&limit=1")
        self.assertEqual(cat_res.status_code, 200)
        items = cat_res.json().get("items", [])
        if items:
            drama_url = items[0]["canonical_url"]
            info_res = self.client.post("/api/drama/info", json={"url": drama_url})
            self.assertEqual(info_res.status_code, 200)
            data = info_res.json()
            self.assertEqual(data.get("provider"), "flextv")
            self.assertIn("drama", data)
            d = data["drama"]
            self.assertIn("title", d)
            self.assertGreater(len(d.get("episodes", [])), 0)

if __name__ == "__main__":
    unittest.main()
