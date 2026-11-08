import sys
from pathlib import Path
from job_scraper.db import Database

for db_path in ['job_archive.db', 'job_questions.db']:
    try:
        p = Path(db_path).resolve()
        print("Testing:", p)
        db = Database(p)
        rows = db.conn.execute("SELECT count(*) FROM job_questions").fetchone()[0]
        print(f"Success! {db_path} has {rows} questions")
        db.close()
    except Exception as e:
        print("Failed:", e)
