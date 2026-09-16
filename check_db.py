import sqlite3

conn = sqlite3.connect("board_questions.db")
cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("Tables:", [r[0] for r in cur.fetchall()])

cur = conn.execute("SELECT COUNT(*) FROM exams")
print("Total exams:", cur.fetchone()[0])

cur = conn.execute("SELECT COUNT(*) FROM questions")
print("Total questions:", cur.fetchone()[0])

print("\nBy class_key and status:")
cur = conn.execute("SELECT class_key, status, COUNT(*) n FROM exams GROUP BY class_key, status")
for r in cur.fetchall():
    print(f"  {r[0]:15s} {r[1]:15s} {r[2]}")

print("\nSample exam rows:")
cur = conn.execute("SELECT id, class_key, board, year, exam_name, subject, status FROM exams LIMIT 5")
for r in cur.fetchall():
    print(f"  {r}")

conn.close()
