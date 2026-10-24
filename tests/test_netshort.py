import unittest
from providers.netshort import NetShortProvider

class TestNetShortProvider(unittest.TestCase):
    def setUp(self):
        self.provider = NetShortProvider()
        self.target_url = "https://netshort.com/zh/episode/%E5%BB%A2%E6%9F%B4%E5%AE%97%E4%B8%BB%E9%A4%8A%E5%87%BA%E4%B9%9D%E5%A4%A7%E5%A5%B3%E5%B8%9D-2105118901192769537"

    def test_can_handle(self):
        self.assertTrue(self.provider.can_handle(self.target_url))
        self.assertFalse(self.provider.can_handle("https://youtube.com/watch?v=123"))

    def test_parse_drama_metadata(self):
        drama = self.provider.get_drama(self.target_url)
        self.assertEqual(drama.title, "廢柴宗主養出九大女帝")
        self.assertEqual(drama.drama_id, "2105118901192769537")
        self.assertGreaterEqual(drama.total_episodes, 50)
        unlocked = [e for e in drama.episodes if not e.is_locked]
        self.assertGreaterEqual(len(unlocked), 10)
        self.assertEqual(drama.episodes[0].episode_no, 1)

if __name__ == "__main__":
    unittest.main()
