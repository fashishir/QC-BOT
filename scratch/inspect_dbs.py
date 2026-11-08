import sqlite3

for db_name in ['job_archive.db', 'job_questions.db']:
    print(f"\n==================== {db_name} ====================")
    try:
        conn = sqlite3.connect(db_name)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [t[0] for t in c.fetchall()]
        print("Tables:", tables)
        for t in tables:
            c.execute(f"SELECT count(*) FROM {t}")
            cnt = c.fetchone()[0]
            print(f"  {t}: {cnt} rows")
            c.execute(f"PRAGMA table_info({t})")
            cols = [col[1] for col in c.fetchall()]
            print(f"    cols: {cols}")
    except Exception as e:
        print("Error:", e)
