"""SQLite storage for the job-exam MCQ archive.

Two databases are used:

* ``job_questions.db`` - raw/local scrape store (gitignored).
* ``job_archive.db``   - validated, publishable copy read by the app.

Both share the same schema. The archive is rebuilt atomically by
:func:`publish_archive` and only contains approved 2025-2026 rows.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .logging_setup import get_logger
from .normalize import now_iso, question_hash, sha256_text

log = get_logger("db")

SCHEMA_VERSION = "1"

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS job_categories (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    slug          TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    display_order INTEGER NOT NULL DEFAULT 0,
    source_url    TEXT
);

CREATE TABLE IF NOT EXISTS job_exams (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source             TEXT NOT NULL,
    source_id          TEXT NOT NULL,
    exam_name          TEXT NOT NULL,
    institution        TEXT,
    post_name          TEXT,
    exam_date          TEXT,
    year               INTEGER NOT NULL CHECK (year IN (2025, 2026)),
    exam_type          TEXT NOT NULL DEFAULT 'mcq',
    total_questions    INTEGER,
    collected_questions INTEGER NOT NULL DEFAULT 0,
    answered_questions INTEGER NOT NULL DEFAULT 0,
    coverage_status    TEXT NOT NULL DEFAULT 'fallback_15'
                       CHECK (coverage_status IN ('full','partial_pdf','fallback_15','missing')),
    is_partial         INTEGER NOT NULL DEFAULT 1 CHECK (is_partial IN (0,1)),
    partial_reason     TEXT,
    source_url         TEXT,
    content_hash       TEXT,
    status             TEXT NOT NULL DEFAULT 'published'
                       CHECK (status IN ('published','upcoming','excluded')),
    first_seen_at      TEXT NOT NULL,
    last_scraped_at    TEXT NOT NULL,
    UNIQUE (source, source_id)
);

CREATE TABLE IF NOT EXISTS job_exam_categories (
    exam_id     INTEGER NOT NULL REFERENCES job_exams(id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES job_categories(id) ON DELETE CASCADE,
    PRIMARY KEY (exam_id, category_id)
);

CREATE TABLE IF NOT EXISTS job_questions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id          INTEGER NOT NULL REFERENCES job_exams(id) ON DELETE CASCADE,
    question_no      INTEGER NOT NULL,
    question_text    TEXT NOT NULL,
    option_1         TEXT,
    option_2         TEXT,
    option_3         TEXT,
    option_4         TEXT,
    answer_index     INTEGER CHECK (answer_index BETWEEN 1 AND 4),
    answer_text      TEXT,
    answer_status    TEXT NOT NULL CHECK (answer_status IN ('published','missing','conflict')),
    answer_source    TEXT NOT NULL,
    answer_confidence TEXT NOT NULL DEFAULT 'high'
                      CHECK (answer_confidence IN ('high','medium','low')),
    review_status    TEXT NOT NULL DEFAULT 'auto'
                      CHECK (review_status IN ('auto','needs_review','approved','rejected')),
    explanation      TEXT,
    images_json      TEXT,
    source_url       TEXT,
    content_hash     TEXT,
    UNIQUE (exam_id, question_no)
);

CREATE TABLE IF NOT EXISTS job_documents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id         INTEGER REFERENCES job_exams(id) ON DELETE CASCADE,
    doc_type        TEXT NOT NULL,
    source_name     TEXT NOT NULL,
    source_url      TEXT NOT NULL,
    local_path      TEXT,
    sha256          TEXT,
    page_count      INTEGER,
    license_status  TEXT NOT NULL CHECK (license_status IN ('approved','unknown','rejected')),
    permission_note TEXT,
    publish_allowed INTEGER NOT NULL CHECK (publish_allowed IN (0,1)),
    parser_version  TEXT,
    imported_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at           TEXT NOT NULL,
    finished_at          TEXT,
    source               TEXT NOT NULL,
    categories_processed INTEGER NOT NULL DEFAULT 0,
    exams_seen           INTEGER NOT NULL DEFAULT 0,
    exams_2025_26        INTEGER NOT NULL DEFAULT 0,
    questions_collected  INTEGER NOT NULL DEFAULT 0,
    answers_found        INTEGER NOT NULL DEFAULT 0,
    errors               INTEGER NOT NULL DEFAULT 0,
    status               TEXT NOT NULL DEFAULT 'running',
    notes                TEXT
);

CREATE TABLE IF NOT EXISTS archive_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_exams_date ON job_exams(exam_date);
CREATE INDEX IF NOT EXISTS idx_exams_year ON job_exams(year);
CREATE INDEX IF NOT EXISTS idx_exams_coverage ON job_exams(coverage_status);
CREATE INDEX IF NOT EXISTS idx_questions_answer ON job_questions(answer_status);
CREATE INDEX IF NOT EXISTS idx_questions_review ON job_questions(review_status);
CREATE INDEX IF NOT EXISTS idx_exam_categories_cat ON job_exam_categories(category_id);
"""

EXAM_COLUMNS = (
    "source", "source_id", "exam_name", "institution", "post_name", "exam_date",
    "year", "exam_type", "total_questions", "collected_questions",
    "answered_questions", "coverage_status", "is_partial", "partial_reason",
    "source_url", "content_hash", "status", "first_seen_at", "last_scraped_at",
)

QUESTION_COLUMNS = (
    "exam_id", "question_no", "question_text", "option_1", "option_2",
    "option_3", "option_4", "answer_index", "answer_text", "answer_status",
    "answer_source", "answer_confidence", "review_status", "explanation",
    "images_json", "source_url", "content_hash",
)


class Database:
    """Thin, explicit SQLite wrapper used by both raw store and archive."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    # ------------------------------------------------------------------ setup
    def initialize(self) -> "Database":
        self.conn.executescript(SCHEMA_SQL)
        self.conn.commit()
        return self

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -------------------------------------------------------------- categories
    def upsert_category(self, slug: str, name: str, display_order: int = 0,
                        source_url: str | None = None) -> int:
        self.conn.execute(
            """
            INSERT INTO job_categories (slug, name, display_order, source_url)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
                name = excluded.name,
                display_order = excluded.display_order,
                source_url = COALESCE(excluded.source_url, job_categories.source_url)
            """,
            (slug, name, display_order, source_url),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT id FROM job_categories WHERE slug = ?", (slug,)).fetchone()
        return int(row["id"])

    def list_categories(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM job_categories ORDER BY display_order, name"
        ).fetchall()

    # ------------------------------------------------------------------- exams
    def upsert_exam(self, exam: dict[str, Any]) -> int:
        """Insert/update an exam keyed by (source, source_id)."""
        now = now_iso()
        data = dict(exam)
        data.setdefault("first_seen_at", now)
        data.setdefault("collected_questions", 0)
        data.setdefault("answered_questions", 0)
        data.setdefault("coverage_status", "fallback_15")
        data.setdefault("is_partial", 1)
        data.setdefault("exam_type", "mcq")
        data.setdefault("status", "published")
        data["last_scraped_at"] = data.get("last_scraped_at") or now
        values = [data.get(col) for col in EXAM_COLUMNS]
        placeholders = ", ".join("?" for _ in EXAM_COLUMNS)
        updates = ", ".join(
            f"{col} = excluded.{col}"
            for col in EXAM_COLUMNS
            if col not in ("source", "source_id", "first_seen_at")
        )
        self.conn.execute(
            f"""
            INSERT INTO job_exams ({", ".join(EXAM_COLUMNS)})
            VALUES ({placeholders})
            ON CONFLICT(source, source_id) DO UPDATE SET {updates}
            """,
            values,
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT id FROM job_exams WHERE source = ? AND source_id = ?",
            (data["source"], data["source_id"]),
        ).fetchone()
        exam_id = int(row["id"])
        self.recount_exam(exam_id)
        return exam_id

    def set_exam_categories(self, exam_id: int, category_ids: Iterable[int]) -> None:
        self.conn.execute("DELETE FROM job_exam_categories WHERE exam_id = ?", (exam_id,))
        self.conn.executemany(
            "INSERT OR IGNORE INTO job_exam_categories (exam_id, category_id) VALUES (?, ?)",
            [(exam_id, int(cid)) for cid in category_ids],
        )
        self.conn.commit()

    def add_exam_category(self, exam_id: int, category_id: int) -> None:
        """Add one category link without dropping existing links.

        One exam can legitimately appear under more than one hub category;
        the scraper uses this additive form so the last category processed
        cannot erase earlier associations.
        """
        self.conn.execute(
            "INSERT OR IGNORE INTO job_exam_categories (exam_id, category_id) VALUES (?, ?)",
            (exam_id, int(category_id)),
        )
        self.conn.commit()

    def get_exam(self, exam_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM job_exams WHERE id = ?", (exam_id,)).fetchone()

    def find_exam(self, source: str, source_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM job_exams WHERE source = ? AND source_id = ?",
            (source, source_id),
        ).fetchone()

    def list_exams(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM job_exams ORDER BY exam_date DESC, exam_name"
        ).fetchall()

    # --------------------------------------------------------------- questions
    def replace_questions(self, exam_id: int, questions: Iterable[dict[str, Any]]) -> int:
        """Replace all questions for one exam; returns rows inserted."""
        rows = []
        for q in questions:
            options = list(q.get("options") or [])
            options = [str(o).strip() for o in options[:4]]
            while len(options) < 4:
                options.append("")
            answer = q.get("answer_index")
            if answer not in (1, 2, 3, 4):
                answer = None
            answer_text = options[answer - 1] if answer else None
            qtext = str(q.get("question_text") or "").strip()
            rows.append((
                exam_id,
                int(q["question_no"]),
                qtext,
                options[0], options[1], options[2], options[3],
                answer,
                answer_text,
                q.get("answer_status") or ("published" if answer else "missing"),
                q.get("answer_source") or "sattacademy",
                q.get("answer_confidence") or "high",
                q.get("review_status") or "auto",
                q.get("explanation"),
                json.dumps(q.get("images") or [], ensure_ascii=False),
                q.get("source_url"),
                q.get("content_hash") or question_hash(qtext, options),
            ))
        self.conn.execute("DELETE FROM job_questions WHERE exam_id = ?", (exam_id,))
        self.conn.executemany(
            f"INSERT INTO job_questions ({', '.join(QUESTION_COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in QUESTION_COLUMNS)})",
            rows,
        )
        self.conn.commit()
        self.recount_exam(exam_id)
        return len(rows)

    def get_questions(self, exam_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM job_questions WHERE exam_id = ? ORDER BY question_no",
            (exam_id,),
        ).fetchall()

    def recount_exam(self, exam_id: int) -> sqlite3.Row | None:
        row = self.get_exam(exam_id)
        if row is None:
            return None
        counts = self.conn.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN answer_status = 'published' THEN 1 ELSE 0 END) AS answered
            FROM job_questions WHERE exam_id = ?
            """,
            (exam_id,),
        ).fetchone()
        total = int(counts["total"] or 0)
        answered = int(counts["answered"] or 0)
        declared = row["total_questions"] or total
        is_partial = 1 if total < declared else 0
        partial_reason = None
        if is_partial:
            partial_reason = row["partial_reason"] or "public_page_limit"
        self.conn.execute(
            """
            UPDATE job_exams SET
                collected_questions = ?,
                answered_questions = ?,
                is_partial = ?,
                partial_reason = ?,
                last_scraped_at = ?
            WHERE id = ?
            """,
            (total, answered, is_partial, partial_reason, now_iso(), exam_id),
        )
        self.conn.commit()
        return self.get_exam(exam_id)

    # --------------------------------------------------------------- documents
    def record_document(self, exam_id: int | None, *, doc_type: str, source_name: str,
                        source_url: str, local_path: str | None = None,
                        sha256: str | None = None, page_count: int | None = None,
                        license_status: str = "approved",
                        permission_note: str | None = None,
                        publish_allowed: bool = True,
                        parser_version: str = "1") -> int:
        cur = self.conn.execute(
            """
            INSERT INTO job_documents
                (exam_id, doc_type, source_name, source_url, local_path, sha256,
                 page_count, license_status, permission_note, publish_allowed,
                 parser_version, imported_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                exam_id, doc_type, source_name, source_url, local_path, sha256,
                page_count, license_status, permission_note,
                1 if publish_allowed else 0, parser_version, now_iso(),
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    # ------------------------------------------------------------------- runs
    def start_run(self, source: str, notes: str | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO scrape_runs (started_at, source, notes) VALUES (?, ?, ?)",
            (now_iso(), source, notes),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_run(self, run_id: int, *, categories: int = 0, exams_seen: int = 0,
                   exams_2025_26: int = 0, questions: int = 0, answers: int = 0,
                   errors: int = 0, status: str = "ok", notes: str | None = None) -> None:
        self.conn.execute(
            """
            UPDATE scrape_runs SET
                finished_at = ?, categories_processed = ?, exams_seen = ?,
                exams_2025_26 = ?, questions_collected = ?, answers_found = ?,
                errors = ?, status = ?, notes = COALESCE(?, notes)
            WHERE id = ?
            """,
            (now_iso(), categories, exams_seen, exams_2025_26, questions,
             answers, errors, status, notes, run_id),
        )
        self.conn.commit()

    # ------------------------------------------------------------------- meta
    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO archive_meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )
        self.conn.commit()

    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM archive_meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    # ----------------------------------------------------------------- counts
    def stats(self) -> dict[str, int]:
        one = lambda sql: int(self.conn.execute(sql).fetchone()[0] or 0)  # noqa: E731
        return {
            "categories": one("SELECT COUNT(*) FROM job_categories"),
            "exams": one("SELECT COUNT(*) FROM job_exams"),
            "questions": one("SELECT COUNT(*) FROM job_questions"),
            "answered": one("SELECT COUNT(*) FROM job_questions WHERE answer_status='published'"),
            "missing": one("SELECT COUNT(*) FROM job_questions WHERE answer_status='missing'"),
            "full_exams": one("SELECT COUNT(*) FROM job_exams WHERE coverage_status='full'"),
            "partial_exams": one("SELECT COUNT(*) FROM job_exams WHERE coverage_status<>'full'"),
        }


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------
def _rows_as_dicts(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def publish_archive(raw_path: str | Path, archive_path: str | Path,
                    *, allow_empty: bool = False) -> dict[str, int]:
    """Build the validated archive from the raw database.

    Gates:
      * only 2025/2026 published exams with at least one question;
      * third-party exams need an approved, publishable document;
      * only questions with review_status auto/approved;
      * explanations are dropped.
    """
    raw_path = Path(raw_path)
    archive_path = Path(archive_path)
    if not raw_path.exists():
        raise FileNotFoundError(f"Raw database not found: {raw_path}")

    raw = sqlite3.connect(raw_path)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA foreign_keys = ON")

    tmp_path = archive_path.with_suffix(archive_path.suffix + ".tmp")
    if tmp_path.exists():
        tmp_path.unlink()
    out = Database(tmp_path).initialize()

    approved_exam_rows: list[dict] = []
    for exam in _rows_as_dicts(raw, "SELECT * FROM job_exams ORDER BY id"):
        if exam["status"] != "published":
            continue
        if exam["year"] not in (2025, 2026):
            continue
        qcount = int(raw.execute(
            "SELECT COUNT(*) FROM job_questions WHERE exam_id = ?", (exam["id"],)
        ).fetchone()[0])
        if qcount == 0:
            continue
        if exam["source"] != "sattacademy":
            doc = raw.execute(
                """
                SELECT 1 FROM job_documents
                WHERE exam_id = ? AND publish_allowed = 1 AND license_status = 'approved'
                LIMIT 1
                """,
                (exam["id"],),
            ).fetchone()
            if doc is None:
                log.warning("Skipping exam %s: no approved document", exam["id"])
                continue
        approved_exam_rows.append(exam)

    # categories
    for cat in _rows_as_dicts(raw, "SELECT * FROM job_categories ORDER BY display_order, id"):
        out.conn.execute(
            "INSERT INTO job_categories (id, slug, name, display_order, source_url) VALUES (?,?,?,?,?)",
            (cat["id"], cat["slug"], cat["name"], cat["display_order"], cat["source_url"]),
        )

    # exams + mappings + questions + documents
    id_map: dict[int, int] = {}
    for exam in approved_exam_rows:
        columns = [c for c in EXAM_COLUMNS if c != "first_seen_at"]
        values = [exam[c] for c in columns]
        out.conn.execute(
            f"INSERT INTO job_exams (id, first_seen_at, {', '.join(columns)}) "
            f"VALUES (?, ?, {', '.join('?' for _ in columns)})",
            [exam["id"], exam["first_seen_at"], *values],
        )
        id_map[exam["id"]] = exam["id"]

    for link in _rows_as_dicts(raw, "SELECT * FROM job_exam_categories"):
        if link["exam_id"] in id_map:
            out.conn.execute(
                "INSERT OR IGNORE INTO job_exam_categories (exam_id, category_id) VALUES (?,?)",
                (link["exam_id"], link["category_id"]),
            )

    for exam in approved_exam_rows:
        questions = _rows_as_dicts(
            raw,
            """
            SELECT * FROM job_questions
            WHERE exam_id = ? AND review_status IN ('auto','approved')
            ORDER BY question_no
            """,
            (exam["id"],),
        )
        for q in questions:
            out.conn.execute(
                """
                INSERT INTO job_questions
                    (exam_id, question_no, question_text, option_1, option_2,
                     option_3, option_4, answer_index, answer_text, answer_status,
                     answer_source, answer_confidence, review_status, explanation,
                     images_json, source_url, content_hash)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    exam["id"], q["question_no"], q["question_text"], q["option_1"],
                    q["option_2"], q["option_3"], q["option_4"], q["answer_index"],
                    q["answer_text"], q["answer_status"], q["answer_source"],
                    q["answer_confidence"], q["review_status"], q.get("explanation"),
                    q["images_json"], q["source_url"], q["content_hash"],
                ),
            )
        docs = _rows_as_dicts(
            raw,
            "SELECT * FROM job_documents WHERE exam_id = ? AND publish_allowed = 1 "
            "AND license_status = 'approved'",
            (exam["id"],),
        )
        for d in docs:
            out.conn.execute(
                """
                INSERT INTO job_documents
                    (exam_id, doc_type, source_name, source_url, local_path, sha256,
                     page_count, license_status, permission_note, publish_allowed,
                     parser_version, imported_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    d["exam_id"], d["doc_type"], d["source_name"], d["source_url"],
                    d["local_path"], d["sha256"], d["page_count"], d["license_status"],
                    d["permission_note"], d["publish_allowed"], d["parser_version"],
                    d["imported_at"],
                ),
            )

    out.conn.commit()

    # recalculate every exam from the published question set
    for exam in approved_exam_rows:
        out.recount_exam(exam["id"])

    stats = out.stats()
    if stats["exams"] == 0 or stats["questions"] == 0:
        out.close()
        tmp_path.unlink(missing_ok=True)
        if not allow_empty:
            raise ValueError("Publish produced an empty archive (use allow_empty=True to override)")

    out.set_meta("schema_version", SCHEMA_VERSION)
    out.set_meta("built_at", now_iso())
    for key in ("exams", "questions", "answered", "missing", "full_exams", "partial_exams"):
        out.set_meta(key, str(stats[key]))

    # integrity checks
    bad_answer = out.conn.execute(
        "SELECT COUNT(*) FROM job_questions WHERE answer_index IS NOT NULL "
        "AND (answer_index < 1 OR answer_index > 4)"
    ).fetchone()[0]
    bad_year = out.conn.execute(
        "SELECT COUNT(*) FROM job_exams WHERE year NOT IN (2025,2026)"
    ).fetchone()[0]
    explanations = out.conn.execute(
        "SELECT COUNT(*) FROM job_questions WHERE explanation IS NOT NULL AND explanation <> ''"
    ).fetchone()[0]
    if bad_answer or bad_year or explanations:
        out.close()
        tmp_path.unlink(missing_ok=True)
        raise ValueError(
            f"Archive integrity failure: bad_answer={bad_answer}, "
            f"bad_year={bad_year}, explanations={explanations}"
        )

    out.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    out.close()
    raw.close()

    os.replace(tmp_path, archive_path)
    log.info("Published archive: %s (%s exams, %s questions, %s answered)",
             archive_path, stats["exams"], stats["questions"], stats["answered"])
    return stats


def archive_summary(path: str | Path) -> dict[str, Any]:
    """Read-only stats + meta for the app header."""
    try:
        db = sqlite3.connect(path)
        db.row_factory = sqlite3.Row
        db.execute("SELECT 1")
    except sqlite3.OperationalError:
        p = Path(path).resolve()
        db = sqlite3.connect(f"file:{p.as_posix()}?immutable=1", uri=True)
        db.row_factory = sqlite3.Row
    stats = {
        "exams": db.execute("SELECT COUNT(*) FROM job_exams").fetchone()[0],
        "questions": db.execute("SELECT COUNT(*) FROM job_questions").fetchone()[0],
        "answered": db.execute(
            "SELECT COUNT(*) FROM job_questions WHERE answer_status='published'"
        ).fetchone()[0],
        "full_exams": db.execute(
            "SELECT COUNT(*) FROM job_exams WHERE coverage_status='full'"
        ).fetchone()[0],
    }
    meta = {row["key"]: row["value"] for row in db.execute("SELECT * FROM archive_meta")}
    categories = db.execute("SELECT COUNT(*) FROM job_categories").fetchone()[0]
    db.close()
    return {"stats": stats, "meta": meta, "categories": categories}


def content_hash_for_exam(parts: Iterable[str]) -> str:
    return sha256_text("|".join(parts))
