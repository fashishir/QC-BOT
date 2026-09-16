import sqlite3

conn = sqlite3.connect("board_questions.db")
cols = [r[1] for r in conn.execute("PRAGMA table_info(exams)").fetchall()]
print("Current columns in exams:", cols)
if "source_type" not in cols:
    conn.execute("ALTER TABLE exams ADD COLUMN source_type TEXT DEFAULT 'board-exam'")
    conn.commit()
    print("Added source_type column to exams successfully.")
else:
    print("source_type already present.")
conn.close()
