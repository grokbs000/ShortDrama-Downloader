import unittest
from providers.tiktok import TikTokShortDramaProvider

class TestTikTokProvider(unittest.TestCase):
    def setUp(self):
        self.provider = TikTokShortDramaProvider()
        self.target_url = "https://www.tiktok.com/shortdrama/episode/7674244050648060949/1"

    def test_can_handle(self):
        self.assertTrue(self.provider.can_handle(self.target_url))
        self.assertFalse(self.provider.can_handle("https://netshort.com/zh/episode/123"))
        self.assertFalse(self.provider.can_handle("https://tiktok.com/@user/video/123"))

    def test_extract_drama_and_episode(self):
        drama_id, ep_no = self.provider.extract_drama_and_episode(self.target_url)
        self.assertEqual(drama_id, "7674244050648060949")
        self.assertEqual(ep_no, 1)

        d2, ep2 = self.provider.extract_drama_and_episode("https://www.tiktok.com/shortdrama/episode/7674244050648060949/15")
        self.assertEqual(d2, "7674244050648060949")
        self.assertEqual(ep2, 15)

if __name__ == "__main__":
    unittest.main()
