import sqlite3

c = sqlite3.connect('file:D:/FA Myself/FA/web screping bot/job_archive.db?immutable=1', uri=True)
c.row_factory = sqlite3.Row
total_q = c.execute("SELECT count(*) FROM job_questions").fetchone()[0]
promo_q = c.execute("SELECT count(*) FROM job_questions WHERE explanation LIKE '%অ্যাপ ইনস্টল%' OR explanation LIKE '%অথেনটিক ব্যাখ্যা%'").fetchone()[0]
empty_expl = c.execute("SELECT count(*) FROM job_questions WHERE explanation IS NULL OR explanation = ''").fetchone()[0]
real_expl = total_q - promo_q - empty_expl
print(f"job_archive.db: total_q={total_q}, promo={promo_q}, empty={empty_expl}, real={real_expl}")
c.close()

c2 = sqlite3.connect('file:D:/FA Myself/FA/web screping bot/job_questions.db?immutable=1', uri=True)
c2.row_factory = sqlite3.Row
total_q2 = c2.execute("SELECT count(*) FROM job_questions").fetchone()[0]
promo_q2 = c2.execute("SELECT count(*) FROM job_questions WHERE explanation LIKE '%অ্যাপ ইনস্টল%' OR explanation LIKE '%অথেনটিক ব্যাখ্যা%'").fetchone()[0]
empty_expl2 = c2.execute("SELECT count(*) FROM job_questions WHERE explanation IS NULL OR explanation = ''").fetchone()[0]
real_expl2 = total_q2 - promo_q2 - empty_expl2
print(f"job_questions.db: total_q={total_q2}, promo={promo_q2}, empty={empty_expl2}, real={real_expl2}")
c2.close()
