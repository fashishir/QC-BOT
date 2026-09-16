"""Publish raw scraped questions to the archive DB read by the Streamlit app.

Two databases live in this project:

  * ``board_questions.db`` -- the raw scrape produced by ``scraper.py``
    (tables: ``exams``, ``questions``). Git-ignored, local only.
  * ``ssc_archive.db``     -- the archive read by ``app.py`` and written by the
    ``ssc_scraper`` package (tables: ``board_exams``, ``exam_questions``).

This script copies exams + questions from the raw DB into the archive DB so
newly scraped questions show up on the live site (https://faqcbot.streamlit.app).
It is idempotent and additive: re-running updates rows in place
(``ON CONFLICT`` on ``mcq_url`` / ``(exam_id, question_type, question_no)``)
and never deletes existing archive rows.

Usage:
  python sync_db.py                     # board_questions.db -> ssc_archive.db
  python sync_db.py --dry-run           # report what would change, write nothing
  python sync_db.py --source other.db --target ssc_archive.db
  python sync_db.py --no-subject-from-name

Field mapping notes:
  * ``subject``      -- taken from the raw DB; when NULL it falls back to
                        ``exam_name`` (sattacademy names a board paper after its
                        subject), which keeps the app's Subject filter useful.
                        Disable with ``--no-subject-from-name``.
  * ``mcq_count`` / ``cq_count`` -- the counts advertised on the site when
                        known, else the number of questions actually stored.
  * ``total_questions`` -- number of questions copied into the archive.
  * ``options_json``  -- normalised to the archive shape
                        ``{"options": [{"index", "text", "images"}], "images": []}``
                        so ``app.py`` renders options and answers.

After a sync, publish the refreshed archive:
  git add ssc_archive.db
  git commit -m "data: refresh board question archive"
  git push
Streamlit Cloud rebuilds the app automatically on push to ``main``.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_SOURCE = Path("board_questions.db")
DEFAULT_TARGET = Path("ssc_archive.db")
DEFAULT_SOURCE_NAME = "sattacademy"


def force_utf8_stdio() -> None:
    """Windows consoles default to a legacy codepage; Bangla names need UTF-8.

    Only called by ``main()`` so that importing this module (e.g. from tests)
    never replaces ``sys.stdout`` / ``sys.stderr``.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

# Archive tables (kept in sync with ssc_scraper/db.py)
ARCHIVE_DDL = """
CREATE TABLE IF NOT EXISTS board_exams (
    id INTEGER PRIMARY KEY AUTOINCREMENT, remote_id TEXT, board TEXT,
    class_key TEXT, exam_name TEXT, subject TEXT, year INTEGER,
    total_questions INTEGER, mcq_count INTEGER, cq_count INTEGER,
    mcq_url TEXT, written_url TEXT, listing_url TEXT,
    source_name TEXT, scraped_at TEXT,
    status TEXT NOT NULL DEFAULT 'discovered',
    missing_reason TEXT, created_at TEXT, updated_at TEXT,
    CONSTRAINT uq_board_exams_url UNIQUE (mcq_url)
);
CREATE INDEX IF NOT EXISTS idx_exams_board ON board_exams (board, year, subject);
CREATE INDEX IF NOT EXISTS idx_exams_status ON board_exams (status);

CREATE TABLE IF NOT EXISTS exam_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id INTEGER REFERENCES board_exams(id),
    remote_ques_id TEXT, question_no INTEGER,
    question_type TEXT, question_text TEXT, options_json TEXT,
    answer TEXT, mcq_url TEXT, written_url TEXT, source_name TEXT,
    scraped_at TEXT,
    CONSTRAINT uq_exam_question UNIQUE (exam_id, question_type, question_no)
);
CREATE INDEX IF NOT EXISTS idx_questions_exam ON exam_questions (exam_id);
"""
def now_iso() -> str:
    """Current UTC timestamp, same shape as the scraper's timestamps."""
    return datetime.now(timezone.utc).isoformat()


def log(msg: str) -> None:
    print(f"[sync] {msg}", flush=True)


# ------------------------------------------------------------------ helpers
def normalise_options(raw: str | None) -> str:
    """Return ``options_json`` in the shape ``app.py`` expects (dict form)."""
    try:
        data = json.loads(raw) if raw else []
    except (TypeError, ValueError):
        data = []
    if isinstance(data, dict):
        payload = dict(data)
        payload["options"] = data.get("options") or []
        payload.setdefault("images", [])
        return json.dumps(payload, ensure_ascii=False)
    options = data if isinstance(data, list) else []
    return json.dumps({"options": options, "images": []}, ensure_ascii=False)


def count_questions(conn: sqlite3.Connection, exam_id: int) -> tuple[int, int]:
    """(mcq_count, written_count) actually stored for a raw exam."""
    row = conn.execute(
        """
        SELECT COUNT(CASE WHEN question_type='mcq' THEN 1 END) AS mcq,
               COUNT(CASE WHEN question_type='written' THEN 1 END) AS cq
        FROM questions WHERE exam_id=?
        """,
        (exam_id,),
    ).fetchone()
    return int(row["mcq"] or 0), int(row["cq"] or 0)

def upsert_exam(conn: sqlite3.Connection, record: dict) -> tuple[int, bool]:
    """Insert/update one board_exams row; return (exam_id, was_new)."""
    existing = conn.execute(
        "SELECT id, created_at FROM board_exams WHERE mcq_url=?", (record["mcq_url"],)
    ).fetchone()
    was_new = existing is None
    created_at = now_iso() if was_new else (existing["created_at"] or now_iso())
    conn.execute(
        """
        INSERT INTO board_exams
            (remote_id, board, class_key, exam_name, subject, year,
             total_questions, mcq_count, cq_count, mcq_url, written_url,
             listing_url, source_name, scraped_at, status, missing_reason,
             created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(mcq_url) DO UPDATE SET
            remote_id=excluded.remote_id,
            board=excluded.board,
            class_key=excluded.class_key,
            exam_name=excluded.exam_name,
            subject=coalesce(excluded.subject, board_exams.subject),
            year=excluded.year,
            total_questions=excluded.total_questions,
            mcq_count=coalesce(excluded.mcq_count, board_exams.mcq_count),
            cq_count=coalesce(excluded.cq_count, board_exams.cq_count),
            written_url=coalesce(excluded.written_url, board_exams.written_url),
            source_name=excluded.source_name,
            scraped_at=excluded.scraped_at,
            status=excluded.status,
            updated_at=excluded.updated_at
        """,
        (
            record["remote_id"], record["board"], record["class_key"],
            record["exam_name"], record["subject"], record["year"],
            record["total_questions"], record["mcq_count"], record["cq_count"],
            record["mcq_url"], record["written_url"], record["listing_url"],
            record["source_name"], record["scraped_at"], record["status"],
            record["missing_reason"], created_at, record["updated_at"],
        ),
    )
    row = conn.execute(
        "SELECT id FROM board_exams WHERE mcq_url=?", (record["mcq_url"],)
    ).fetchone()
    return int(row["id"]), was_new


def upsert_question(conn: sqlite3.Connection, record: dict) -> bool:
    """Insert/update one exam_questions row; return True when newly inserted."""
    existing = conn.execute(
        "SELECT 1 FROM exam_questions WHERE exam_id=? AND question_type=? AND question_no=?",
        (record["exam_id"], record["question_type"], record["question_no"]),
    ).fetchone()
    conn.execute(
        """
        INSERT INTO exam_questions
            (exam_id, remote_ques_id, question_no, question_type, question_text,
             options_json, answer, mcq_url, written_url, source_name, scraped_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(exam_id, question_type, question_no) DO UPDATE SET
            question_text=excluded.question_text,
            options_json=excluded.options_json,
            answer=excluded.answer,
            mcq_url=excluded.mcq_url,
            written_url=excluded.written_url,
            source_name=excluded.source_name,
            scraped_at=excluded.scraped_at
        """,
        (
            record["exam_id"], record["remote_ques_id"], record["question_no"],
            record["question_type"], record["question_text"],
            record["options_json"], record["answer"], record["mcq_url"],
            record["written_url"], record["source_name"], record["scraped_at"],
        ),
    )
    return existing is None

# ------------------------------------------------------------------ sync
def sync(
    source_path: Path = DEFAULT_SOURCE,
    target_path: Path = DEFAULT_TARGET,
    *,
    source_name: str = DEFAULT_SOURCE_NAME,
    subject_from_name: bool = True,
    dry_run: bool = False,
) -> dict[str, int]:
    """Copy exams/questions from the raw scrape DB into the archive DB."""
    stats = {"exams_new": 0, "exams_updated": 0,
             "questions_new": 0, "questions_updated": 0}
    if not source_path.exists() or source_path.stat().st_size == 0:
        raise FileNotFoundError(
            f"raw scrape DB not found: {source_path} - run `python scraper.py` first"
        )

    source = sqlite3.connect(f"file:{source_path.resolve()}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    target = sqlite3.connect(str(target_path))
    target.row_factory = sqlite3.Row

    try:
        target.executescript(ARCHIVE_DDL)
        before_exams = target.execute("SELECT COUNT(*) FROM board_exams").fetchone()[0]
        before_questions = target.execute("SELECT COUNT(*) FROM exam_questions").fetchone()[0]

        for exam in source.execute("SELECT * FROM exams ORDER BY id").fetchall():
            raw = dict(exam)
            raw_id = raw["id"]
            stored_mcq, stored_cq = count_questions(source, raw_id)
            subject = raw.get("subject")
            if not subject and subject_from_name:
                subject = raw.get("exam_name")
            stamp = now_iso()
            record = {
                "remote_id": raw.get("remote_id"),
                "board": raw.get("board"),
                "class_key": raw.get("class_key"),
                "exam_name": raw.get("exam_name"),
                "subject": subject,
                "year": raw.get("year"),
                "total_questions": stored_mcq + stored_cq,
                "mcq_count": raw.get("mcq_count") if raw.get("mcq_count") is not None else stored_mcq or None,
                "cq_count": raw.get("cq_count") if raw.get("cq_count") is not None else stored_cq or None,
                "mcq_url": raw.get("mcq_url") or "",
                "written_url": raw.get("written_url"),
                "listing_url": None,
                "source_name": source_name,
                "scraped_at": raw.get("scraped_at") or stamp,
                "status": raw.get("status") or "listed",
                "missing_reason": None,
                "updated_at": stamp,
            }

            if dry_run:
                archived = target.execute(
                    "SELECT id FROM board_exams WHERE mcq_url=?", (record["mcq_url"],)
                ).fetchone()
                was_new = archived is None
                exam_id = -1 if archived is None else int(archived["id"])
            else:
                exam_id, was_new = upsert_exam(target, record)
            stats["exams_new" if was_new else "exams_updated"] += 1
            log(f"exam {'+' if was_new else '~'} {record['board']} {record['year']} "
                f"{record['exam_name']} ({stored_mcq} mcq / {stored_cq} cq)"
                + ("  [dry-run]" if dry_run else ""))

            questions = source.execute(
                "SELECT * FROM questions WHERE exam_id=? ORDER BY question_type, question_no",
                (raw_id,),
            ).fetchall()
            for q in questions:
                row = dict(q)
                qtype = row.get("question_type") or "mcq"
                source_url = row.get("source_url")
                if qtype == "written":
                    mcq_url, written_url = None, record["written_url"] or source_url
                else:
                    mcq_url, written_url = record["mcq_url"] or source_url, None
                question_record = {
                    "exam_id": exam_id,
                    "remote_ques_id": None,
                    "question_no": row.get("question_no"),
                    "question_type": qtype,
                    "question_text": row.get("question_text"),
                    "options_json": normalise_options(row.get("options_json")),
                    "answer": row.get("correct_answer"),
                    "mcq_url": mcq_url,
                    "written_url": written_url,
                    "source_name": source_name,
                    "scraped_at": row.get("scraped_at") or record["scraped_at"],
                }
                if dry_run:
                    inserted = target.execute(
                        "SELECT 1 FROM exam_questions WHERE exam_id=? AND"
                        " question_type=? AND question_no=?",
                        (exam_id, qtype, row.get("question_no")),
                    ).fetchone() is None
                else:
                    inserted = upsert_question(target, question_record)
                stats["questions_new" if inserted else "questions_updated"] += 1

        if dry_run:
            target.rollback()
        else:
            target.commit()
            # keep the on-disk archive self-contained: no stray -wal / -shm files
            target.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            target.commit()
            target.execute("PRAGMA journal_mode=DELETE")
            target.commit()
            target.execute("VACUUM")
            target.commit()

        after_exams = target.execute("SELECT COUNT(*) FROM board_exams").fetchone()[0]
        after_questions = target.execute("SELECT COUNT(*) FROM exam_questions").fetchone()[0]
        suffix = "  [dry-run, unchanged]" if dry_run else ""
        log(f"archive exams    : {before_exams} -> {after_exams}{suffix}")
        log(f"archive questions: {before_questions} -> {after_questions}{suffix}")
        log(f"exams new/updated     : {stats['exams_new']} / {stats['exams_updated']}")
        log(f"questions new/updated : {stats['questions_new']} / {stats['questions_updated']}")
    finally:
        source.close()
        target.close()
    return stats


# ------------------------------------------------------------------ cli
def main(argv: list[str] | None = None) -> int:
    force_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="Sync board_questions.db (raw scrape) into ssc_archive.db (app DB)."
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE,
                        help="raw scrape DB written by scraper.py (default: board_questions.db)")
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET,
                        help="archive DB read by app.py (default: ssc_archive.db)")
    parser.add_argument("--source-name", default=DEFAULT_SOURCE_NAME,
                        help="source_name stored on imported rows (default: sattacademy)")
    parser.add_argument("--subject-from-name", dest="subject_from_name",
                        action="store_true", default=True,
                        help="fall back to exam_name when subject is NULL (default)")
    parser.add_argument("--no-subject-from-name", dest="subject_from_name",
                        action="store_false",
                        help="keep subject NULL when the raw scrape has none")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would change without writing")
    args = parser.parse_args(argv)

    try:
        sync(args.source, args.target,
             source_name=args.source_name,
             subject_from_name=args.subject_from_name,
             dry_run=args.dry_run)
    except FileNotFoundError as exc:
        log(f"ERROR: {exc}")
        return 1

    if args.dry_run:
        log("dry-run complete - nothing was written")
    else:
        log(f"done - publish {args.target} (git add / commit / push) to update the live app")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
