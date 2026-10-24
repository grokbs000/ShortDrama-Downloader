import unittest
from fastapi.testclient import TestClient
from pathlib import Path
import shutil
import json

from app import app
from core.db import db
from core.config import settings

class TestSidebarFeatures(unittest.TestCase):
    def setUp(self):
        db.init()
        self.client = TestClient(app)

    def test_settings_api(self):
        # Test GET /api/settings
        res = self.client.get("/api/settings")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("download_dir", data)
        self.assertIn("ffmpeg_available", data)

        # Test POST /api/settings (update download directory)
        test_dir = str(Path(__file__).parent / "test_downloads")
        res_post = self.client.post("/api/settings", json={"download_dir": test_dir})
        self.assertEqual(res_post.status_code, 200)
        self.assertEqual(res_post.json()["download_dir"], str(Path(test_dir).resolve()))
        self.assertTrue(Path(test_dir).exists())
        
        # Cleanup test dir
        if Path(test_dir).exists():
            shutil.rmtree(test_dir, ignore_errors=True)

    def test_auth_api(self):
        # Test GET /api/auth/status
        res = self.client.get("/api/auth/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("netshort", data)
        self.assertIn("tiktok", data)

        # Test POST /api/auth/save
        test_payload = {"provider": "tiktok", "auth_data": json.dumps({"cookies": [{"name": "sid", "value": "xyz"}]})}
        res_save = self.client.post("/api/auth/save", json=test_payload)
        self.assertEqual(res_save.status_code, 200)
        self.assertTrue(res_save.json()["ok"])

        # Check status again
        res_after = self.client.get("/api/auth/status")
        self.assertTrue(res_after.json()["tiktok"]["configured"])

        # Test POST /api/auth/clear
        res_clear = self.client.post("/api/auth/clear", json={"provider": "tiktok"})
        self.assertEqual(res_clear.status_code, 200)
        
        res_final = self.client.get("/api/auth/status")
        self.assertFalse(res_final.json()["tiktok"]["configured"])

    def test_task_retry_and_clear_api(self):
        # Create a mock failed task in DB
        tid = db.add_task("https://x.test/fail.mp4", "FailDrama", 1, "best")
        db.update_task(tid, status="failed", error="mock error")
        
        # Retry task
        res_retry = self.client.post(f"/api/tasks/{tid}/retry")
        self.assertEqual(res_retry.status_code, 200)
        task_info = db.get_task(tid)
        self.assertIn(task_info["status"], ("queued", "running", "failed"))

        # Mark completed & test clear_completed
        db.update_task(tid, status="completed", progress=100)
        res_clear_comp = self.client.post("/api/tasks/clear_completed")
        self.assertEqual(res_clear_comp.status_code, 200)
        self.assertIsNone(db.get_task(tid))

    def test_catalog_pagination_api(self):
        res = self.client.get("/api/tiktok/catalog?offset=0&limit=5")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("ok"))
        self.assertIn("items", data)
        self.assertIn("has_more", data)
        self.assertLessEqual(len(data["items"]), 5)

    def test_concurrency_settings(self):
        res = self.client.post("/api/settings", json={"concurrency": 4})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["concurrency"], 4)
        get_res = self.client.get("/api/settings")
        self.assertEqual(get_res.json()["concurrency"], 4)

    def test_bulk_tasks_control_api(self):
        t1 = db.add_task("https://x.test/t1.mp4", "BulkDrama", 1, "best")
        t2 = db.add_task("https://x.test/t2.mp4", "BulkDrama", 2, "best")
        db.update_task(t1, status="failed", error="err1")
        db.update_task(t2, status="failed", error="err2")

        res_retry_all = self.client.post("/api/tasks/retry_all_failed")
        self.assertEqual(res_retry_all.status_code, 200)
        self.assertGreaterEqual(res_retry_all.json()["count"], 2)

        res_cancel_all = self.client.post("/api/tasks/cancel_all")
        self.assertEqual(res_cancel_all.status_code, 200)
        self.assertGreaterEqual(res_cancel_all.json()["count"], 0)

        # Cleanup
        db.delete_task(t1)
        db.delete_task(t2)

if __name__ == "__main__":
    unittest.main()
