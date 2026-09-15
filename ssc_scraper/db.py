"""Storage layer: SQLite by default, optional PostgreSQL.

Every paper row keeps full source attribution (file_url, source_page_url,
source_name, timestamps) so every archived file can be credited to its
origin. The class exposes a small backend-neutral interface; SQLite needs
no extra dependencies while PostgreSQL requires psycopg2 (optional extra).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .config import DatabaseConfig
from .logging_setup import get_logger
from .models import STATUSES, SUCCESS_STATUSES
from .utils import now_iso

log = get_logger("db")

# Writable columns of the papers table (excluding id / created_at / updated_at)
PAPER_COLUMNS = (
    "board", "year", "subject", "paper_type", "exam_code", "set_code", "shift",
    "language", "file_url", "source_page_url", "source_name", "downloaded_at",
    "file_name", "file_path", "file_hash", "file_size", "page_count",
    "ocr_text", "ocr_confidence", "status", "missing_reason",
)


class Database:
    """Backend-neutral database facade (SQLite | PostgreSQL)."""

    def __init__(self, cfg: DatabaseConfig):
        self.cfg = cfg
        self.backend = (cfg.backend or "sqlite").lower()
        if self.backend in ("postgres", "postgresql"):
            self.backend = "postgres"
        elif self.backend != "sqlite":
            raise ValueError(f"Unsupported database backend: {cfg.backend!r}")
        self.conn = None

    # ------------------------------------------------------------- connection
    def connect(self):
        if self.conn is not None:
            return self.conn
        if self.backend == "sqlite":
            path = Path(self.cfg.sqlite_path)
            if str(path.parent):
                path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(str(path))
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA journal_mode=WAL")
        else:
            try:
                import psycopg2
                import psycopg2.extras  # noqa: F401
            except ImportError as exc:
                raise RuntimeError(
                    "PostgreSQL backend selected but psycopg2 is not installed. "
                    "Run: pip install psycopg2-binary"
                ) from exc
            if not self.cfg.postgres_dsn:
                raise ValueError("database.postgres_dsn is required for the postgres backend")
            self.conn = psycopg2.connect(self.cfg.postgres_dsn)
        return self.conn

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def commit(self) -> None:
        if self.conn is not None:
            self.conn.commit()

    @property
    def _ph(self) -> str:
        return "%s" if self.backend == "postgres" else "?"

    def _execute(self, sql: str, params=(), fetch: str | None = None):
        if self.backend == "postgres":
            import psycopg2.extras
            cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            cur = self.conn.cursor()
        cur.execute(sql, tuple(params))
        rows = None
        if fetch == "one":
            rows = cur.fetchone()
        elif fetch == "all":
            rows = cur.fetchall()
        return cur, rows

    # ----------------------------------------------------------------- schema
    def create_schema(self) -> None:
        self.connect()
        pk = "INTEGER PRIMARY KEY AUTOINCREMENT" if self.backend == "sqlite" else "BIGSERIAL PRIMARY KEY"
        ddl = """
        CREATE TABLE IF NOT EXISTS papers (
            id {pk},
            board TEXT, year INTEGER, subject TEXT, paper_type TEXT,
            exam_code TEXT, set_code TEXT, shift TEXT, language TEXT,
            file_url TEXT NOT NULL, source_page_url TEXT, source_name TEXT,
            downloaded_at TEXT, file_name TEXT, file_path TEXT, file_hash TEXT,
            file_size INTEGER, page_count INTEGER, ocr_text TEXT,
            ocr_confidence REAL, status TEXT NOT NULL DEFAULT 'discovered',
            missing_reason TEXT, created_at TEXT, updated_at TEXT,
            CONSTRAINT uq_papers_file_url UNIQUE (file_url)
        );
        CREATE INDEX IF NOT EXISTS idx_papers_hash ON papers (file_hash);
        CREATE INDEX IF NOT EXISTS idx_papers_combo ON papers (board, year, subject);
        CREATE INDEX IF NOT EXISTS idx_papers_status ON papers (status);

        CREATE TABLE IF NOT EXISTS sources (
            id {pk}, name TEXT NOT NULL, base_url TEXT, enabled INTEGER DEFAULT 1,
            status TEXT DEFAULT 'active', notes TEXT, created_at TEXT,
            CONSTRAINT uq_sources_name UNIQUE (name)
        );

        CREATE TABLE IF NOT EXISTS crawl_state (
            url TEXT NOT NULL PRIMARY KEY,
            source_name TEXT, status TEXT DEFAULT 'pending', depth INTEGER DEFAULT 0,
            found_on TEXT, context TEXT, discovered_at TEXT, updated_at TEXT,
            last_error TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_crawl_status ON crawl_state (source_name, status);

        CREATE TABLE IF NOT EXISTS run_log (
            id {pk}, command TEXT, started_at TEXT, finished_at TEXT,
            summary_json TEXT
        );
        """.replace("{pk}", pk)
        if self.backend == "sqlite":
            self.conn.executescript(ddl)
        else:
            cur = self.conn.cursor()
            cur.execute(ddl)
        self.commit()
        log.debug("Schema ensured (%s backend)", self.backend)

    # ----------------------------------------------------------------- papers
    def upsert_paper(self, record: dict) -> int:
        """Insert or update a paper keyed by its unique file_url; return its id."""
        values = {k: record.get(k) for k in PAPER_COLUMNS}
        values["file_url"] = values.get("file_url") or ""
        values["status"] = values.get("status") or "discovered"
        if values["status"] not in STATUSES:
            raise ValueError(f"Invalid paper status: {values['status']!r}")
        cols = list(values)
        placeholders = ", ".join([self._ph] * len(cols))
        update_set = ", ".join(f"{c} = excluded.{c}" for c in cols if c != "file_url")
        sql = (
            f"INSERT INTO papers ({', '.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT(file_url) DO UPDATE SET {update_set}"
        )
        self._execute(sql, list(values.values()))
        self.commit()
        _, row = self._execute(
            f"SELECT id FROM papers WHERE file_url = {self._ph}",
            (values["file_url"],),
            fetch="one",
        )
        return row["id"]

    def update_paper(self, paper_id: int, **fields) -> None:
        """Update selected columns of one paper row."""
        if not fields:
            return
        unknown = set(fields) - set(PAPER_COLUMNS) - {"updated_at", "created_at"}
        if unknown:
            raise ValueError(f"Unknown paper columns: {sorted(unknown)}")
        if "status" in fields and fields["status"] not in STATUSES:
            raise ValueError(f"Invalid paper status: {fields['status']!r}")
        fields.setdefault("updated_at", now_iso())
        assignments = ", ".join(f"{k} = {self._ph}" for k in fields)
        self._execute(
            f"UPDATE papers SET {assignments} WHERE id = {self._ph}",
            [*fields.values(), paper_id],
        )
        self.commit()

    def get_paper_by_url(self, url: str):
        _, row = self._execute(
            f"SELECT * FROM papers WHERE file_url = {self._ph}", (url,), fetch="one"
        )
        return dict(row) if row else None

    def get_paper_by_hash(self, file_hash: str, exclude_id: int | None = None):
        sql = f"SELECT * FROM papers WHERE file_hash = {self._ph}"
        params = [file_hash]
        if exclude_id is not None:
            sql += f" AND id <> {self._ph}"
            params.append(exclude_id)
        sql += f" LIMIT 1"
        _, row = self._execute(sql, params, fetch="one")
        return dict(row) if row else None

    def get_paper_by_signature(self, signature_parts: dict, exclude_id: int | None = None):
        """Find a successful paper with the same normalized board/year/subject/paper_type."""
        sql = (
            "SELECT * FROM papers WHERE lower(board) = {p} AND year = {p} "
            "AND lower(subject) = {p} AND lower(coalesce(paper_type, 'unknown')) = {p} "
            "AND status IN ({statuses})"
        ).format(p=self._ph, statuses=", ".join([self._ph] * len(SUCCESS_STATUSES)))
        params = [
            (signature_parts.get("board") or "").lower(),
            signature_parts.get("year"),
            (signature_parts.get("subject") or "").lower(),
            (signature_parts.get("paper_type") or "unknown").lower(),
            *SUCCESS_STATUSES,
        ]
        if exclude_id is not None:
            sql += f" AND id <> {self._ph}"
            params.append(exclude_id)
        sql += " ORDER BY id LIMIT 1"
        _, row = self._execute(sql, params, fetch="one")
        return dict(row) if row else None

    def iter_papers(self, statuses=None, source_name=None, has_file=False):
        """Yield paper rows (as dicts) matching the given filters."""
        clauses, params = [], []
        if statuses:
            clauses.append("status IN ({})".format(", ".join([self._ph] * len(statuses))))
            params.extend(statuses)
        if source_name:
            clauses.append(f"source_name = {self._ph}")
            params.append(source_name)
        if has_file:
            clauses.append("file_path IS NOT NULL")
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        _, rows = self._execute(
            f"SELECT * FROM papers{where} ORDER BY id", params, fetch="all"
        )
        return [dict(r) for r in (rows or [])]

    # -------------------------------------------------------------- reporting
    def count_by_status(self) -> dict[str, int]:
        _, rows = self._execute(
            "SELECT status, COUNT(*) AS n FROM papers GROUP BY status", fetch="all"
        )
        return {r["status"]: r["n"] for r in (rows or [])}

    def count_by_field(self, field: str, statuses=SUCCESS_STATUSES) -> dict[str, int]:
        """Count successful papers grouped by a facet (whitelisted field)."""
        allowed = ("board", "year", "subject", "paper_type", "language", "source_name")
        if field not in allowed:
            raise ValueError(f"count_by_field only supports {allowed}")
        placeholders = ", ".join([self._ph] * len(statuses))
        _, rows = self._execute(
            f"SELECT {field} AS value, COUNT(*) AS n FROM papers "
            f"WHERE status IN ({placeholders}) AND {field} IS NOT NULL "
            f"GROUP BY {field} ORDER BY n DESC",
            [*statuses],
            fetch="all",
        )
        return {str(r["value"]): r["n"] for r in (rows or [])}

    def distinct_combos(self):
        """Distinct (board, year, subject) triples that were successfully collected."""
        placeholders = ", ".join([self._ph] * len(SUCCESS_STATUSES))
        _, rows = self._execute(
            f"SELECT DISTINCT board, year, subject FROM papers "
            f"WHERE status IN ({placeholders}) "
            f"AND board IS NOT NULL AND year IS NOT NULL AND subject IS NOT NULL",
            [*SUCCESS_STATUSES],
            fetch="all",
        )
        return [(r["board"], r["year"], r["subject"]) for r in (rows or [])]

    # ------------------------------------------------------------ crawl state
    def set_crawl_state(self, url: str, source_name: str, status: str,
                        depth: int = 0, found_on: str | None = None,
                        context: str | None = None, error: str | None = None) -> None:
        now = now_iso()
        sql = (
            f"INSERT INTO crawl_state (url, source_name, status, depth, found_on, "
            f"context, discovered_at, updated_at, last_error) "
            f"VALUES ({self._ph}, {self._ph}, {self._ph}, {self._ph}, {self._ph}, "
            f"{self._ph}, {self._ph}, {self._ph}, {self._ph}) "
            f"ON CONFLICT(url) DO UPDATE SET source_name = excluded.source_name, "
            f"status = excluded.status, depth = excluded.depth, "
            f"found_on = coalesce(excluded.found_on, found_on), "
            f"context = coalesce(excluded.context, context), "
            f"updated_at = excluded.updated_at, last_error = excluded.last_error"
        )
        self._execute(sql, [url, source_name, status, depth, found_on, context, now, now, error])
        self.commit()

    def get_crawl_state(self, url: str):
        _, row = self._execute(
            f"SELECT * FROM crawl_state WHERE url = {self._ph}", (url,), fetch="one"
        )
        return dict(row) if row else None

    def iter_crawl(self, source_name=None, statuses=None) -> list[dict]:
        clauses, params = [], []
        if source_name:
            clauses.append(f"source_name = {self._ph}")
            params.append(source_name)
        if statuses:
            clauses.append("status IN ({})".format(", ".join([self._ph] * len(statuses))))
            params.extend(statuses)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        _, rows = self._execute(
            f"SELECT * FROM crawl_state{where} ORDER BY depth, url", params, fetch="all"
        )
        return [dict(r) for r in (rows or [])]

    def count_crawl(self, source_name: str | None = None, status: str | None = None) -> int:
        clauses, params = [], []
        if source_name:
            clauses.append(f"source_name = {self._ph}")
            params.append(source_name)
        if status:
            clauses.append(f"status = {self._ph}")
            params.append(status)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        _, row = self._execute(
            f"SELECT COUNT(*) AS n FROM crawl_state{where}", params, fetch="one"
        )
        return row["n"]

    # ---------------------------------------------------------------- sources
    def upsert_source(self, name: str, base_url: str = "", enabled: bool = True,
                      status: str = "active", notes: str | None = None) -> None:
        sql = (
            f"INSERT INTO sources (name, base_url, enabled, status, notes, created_at) "
            f"VALUES ({self._ph}, {self._ph}, {self._ph}, {self._ph}, {self._ph}, {self._ph}) "
            f"ON CONFLICT(name) DO UPDATE SET base_url = excluded.base_url, "
            f"enabled = excluded.enabled, status = excluded.status, "
            f"notes = coalesce(excluded.notes, notes)"
        )
        self._execute(sql, [name, base_url, int(bool(enabled)), status, notes, now_iso()])
        self.commit()

    def set_source_status(self, name: str, status: str, note: str | None = None) -> None:
        fields = [f"status = {self._ph}"]
        params: list = [status]
        if note:
            fields.append(f"notes = coalesce(notes || ' | ', '') || {self._ph}")
            params.append(note)
        self._execute(f"UPDATE sources SET {', '.join(fields)} WHERE name = {self._ph}",
                      [*params, name])
        self.commit()
        if status == "manual_review":
            log.warning("Source %r marked for MANUAL REVIEW: %s", name, note or status)

    # ---------------------------------------------------------------- run log
    def log_run(self, command: str, started_at: str, summary: dict) -> None:
        self._execute(
            f"INSERT INTO run_log (command, started_at, finished_at, summary_json) "
            f"VALUES ({self._ph}, {self._ph}, {self._ph}, {self._ph})",
            [command, started_at, now_iso(), json.dumps(summary, ensure_ascii=False, default=str)],
        )
        self.commit()
