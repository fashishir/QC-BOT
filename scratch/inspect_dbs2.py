import os
import sqlite3

p1 = os.path.abspath('job_archive.db')
p2 = os.path.abspath('job_questions.db')
print("p1:", p1, "exists:", os.path.exists(p1), "size:", os.path.getsize(p1))
print("p2:", p2, "exists:", os.path.exists(p2), "size:", os.path.getsize(p2))

try:
    conn = sqlite3.connect(f"file:{p1}?mode=ro", uri=True)
    c = conn.cursor()
    c.execute("SELECT count(*) FROM sqlite_master")
    print("job_archive master count:", c.fetchone()[0])
except Exception as e:
    print("Error p1:", e)

try:
    conn = sqlite3.connect(f"file:{p2}?mode=ro", uri=True)
    c = conn.cursor()
    c.execute("SELECT count(*) FROM sqlite_master")
    print("job_questions master count:", c.fetchone()[0])
except Exception as e:
    print("Error p2:", e)
