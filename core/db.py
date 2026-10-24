import sqlite3
from pathlib import Path
from core.config import settings

class DB:
    def connect(self):
        c = sqlite3.connect(settings.db_path, timeout=30.0)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL;")
        c.execute("PRAGMA synchronous=NORMAL;")
        c.execute("PRAGMA busy_timeout=30000;")
        return c

    def init(self):
        with self.connect() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS dramas(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              title TEXT NOT NULL,
              source TEXT DEFAULT '',
              source_id TEXT DEFAULT '',
              detail_url TEXT DEFAULT '',
              cover_url TEXT DEFAULT '',
              created_at TEXT DEFAULT CURRENT_TIMESTAMP,
              UNIQUE(source, source_id)
            );
            CREATE TABLE IF NOT EXISTS episodes(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              drama_id INTEGER,
              episode_number INTEGER NOT NULL,
              title TEXT DEFAULT '',
              page_url TEXT NOT NULL,
              duration REAL,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP,
              UNIQUE(drama_id, episode_number, page_url)
            );
            CREATE TABLE IF NOT EXISTS media_sources(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              episode_id INTEGER,
              url TEXT NOT NULL,
              kind TEXT,
              content_type TEXT,
              quality TEXT,
              width INTEGER,
              height INTEGER,
              fps REAL,
              bitrate INTEGER,
              size INTEGER,
              score INTEGER DEFAULT 0,
              source TEXT,
              referer TEXT,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS tasks(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              url TEXT NOT NULL,
              title TEXT,
              episode INTEGER,
              quality TEXT,
              status TEXT DEFAULT 'queued',
              progress REAL DEFAULT 0,
              output TEXT DEFAULT '',
              error TEXT DEFAULT '',
              created_at TEXT DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS history(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              task_id INTEGER,
              title TEXT,
              episode INTEGER,
              output TEXT,
              status TEXT,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_tasks_updated ON tasks(updated_at);
            CREATE INDEX IF NOT EXISTS idx_episodes_drama ON episodes(drama_id);
            CREATE INDEX IF NOT EXISTS idx_history_status ON history(status);
            """)

    def add_task(self, url, title, episode, quality):
        with self.connect() as c:
            cur = c.execute(
                "INSERT INTO tasks(url,title,episode,quality) VALUES(?,?,?,?)",
                (url,title,episode,quality))
            return cur.lastrowid

    def get_task(self, task_id):
        with self.connect() as c:
            r = c.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            return dict(r) if r else None

    def update_task(self, task_id, **kwargs):
        if not kwargs: return
        kwargs["updated_at"] = "CURRENT_TIMESTAMP"
        sets, vals = [], []
        for k,v in kwargs.items():
            if v == "CURRENT_TIMESTAMP":
                sets.append(f"{k}=CURRENT_TIMESTAMP")
            else:
                sets.append(f"{k}=?"); vals.append(v)
        vals.append(task_id)
        with self.connect() as c:
            c.execute(f"UPDATE tasks SET {','.join(sets)} WHERE id=?", vals)

    def add_history(self, task):
        with self.connect() as c:
            c.execute(
                "INSERT INTO history(task_id,title,episode,output,status) VALUES(?,?,?,?,?)",
                (task["id"], task["title"], task["episode"], task.get("output",""), task["status"]))

    def list_tasks(self):
        with self.connect() as c:
            return [dict(r) for r in c.execute("SELECT * FROM tasks ORDER BY id DESC").fetchall()]

    def delete_task(self, task_id: int):
        with self.connect() as c:
            c.execute("DELETE FROM tasks WHERE id=?", (task_id,))
            return True

    def clear_completed_tasks(self):
        with self.connect() as c:
            c.execute("DELETE FROM tasks WHERE status='completed'")
            return True

    def clear_all_tasks(self):
        with self.connect() as c:
            c.execute("DELETE FROM tasks")
            return True

    def reset_task_for_retry(self, task_id: int):
        with self.connect() as c:
            c.execute("UPDATE tasks SET status='queued', progress=0, error='', updated_at=CURRENT_TIMESTAMP WHERE id=?", (task_id,))
            return True

    def retry_all_failed_tasks(self):
        with self.connect() as c:
            rows = c.execute("SELECT id FROM tasks WHERE status='failed'").fetchall()
            ids = [r["id"] for r in rows]
            if ids:
                c.execute("UPDATE tasks SET status='queued', progress=0, error='', updated_at=CURRENT_TIMESTAMP WHERE status='failed'")
            return ids

    def cancel_all_active_tasks(self):
        with self.connect() as c:
            rows = c.execute("SELECT id FROM tasks WHERE status IN ('queued', 'running')").fetchall()
            ids = [r["id"] for r in rows]
            if ids:
                c.execute("UPDATE tasks SET status='cancelled', updated_at=CURRENT_TIMESTAMP WHERE status IN ('queued', 'running')")
            return ids

    def list_history(self):
        with self.connect() as c:
            return [dict(r) for r in c.execute("SELECT * FROM history ORDER BY id DESC").fetchall()]

    def clear_history(self):
        with self.connect() as c:
            c.execute("DELETE FROM history")
            return True

    def get_downloaded_map(self):
        """Return sets of completed URLs, downloaded drama titles, and episode numbers."""
        with self.connect() as c:
            rows = c.execute("SELECT id, url, title, episode, output, status FROM tasks WHERE status='completed'").fetchall()

        completed_urls = set()
        drama_episodes = {}
        downloaded_dramas = set()

        for r in rows:
            url = r["url"]
            title = r["title"]
            ep = r["episode"]
            output = r["output"]

            # Double check output file exists on disk if output path is recorded
            if output:
                p = Path(output)
                if not p.exists() or p.stat().st_size < 100 * 1024:
                    continue

            if url:
                completed_urls.add(url)
            if title:
                downloaded_dramas.add(title)
                if title not in drama_episodes:
                    drama_episodes[title] = set()
                if ep is not None:
                    drama_episodes[title].add(int(ep))

        return {
            "completed_urls": list(completed_urls),
            "downloaded_dramas": list(downloaded_dramas),
            "drama_episodes": {k: sorted(list(v)) for k, v in drama_episodes.items()}
        }

db = DB()
