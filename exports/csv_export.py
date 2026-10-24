import csv, io
from core.db import db

def _csv(rows):
    out=io.StringIO()
    if not rows: return b""
    w=csv.DictWriter(out,fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)
    return ("\ufeff"+out.getvalue()).encode("utf-8")

def export_tasks_csv():
    return _csv(db.list_tasks())

def export_episodes_csv():
    rows=[]
    with db.connect() as c:
        rows=[dict(r) for r in c.execute("SELECT * FROM episodes ORDER BY drama_id,episode_number").fetchall()]
    return _csv(rows)
