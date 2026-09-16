"""Smoke test: the Streamlit app renders from the committed archive DB."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
ARCHIVE = ROOT / "ssc_archive.db"


@pytest.mark.skipif(not ARCHIVE.exists(), reason="ssc_archive.db not present")
def test_app_renders_board_exams():
    at = AppTest.from_file(str(APP), default_timeout=180).run()

    assert not at.exception, [f"{e.type}: {e.message}" for e in at.exception]
    # the filter header from the screenshots: Level / Subject / Board / Type / Year
    assert [s.label for s in at.selectbox][:3] == ["Level", "Subject", "Board"]
    assert at.selectbox[0].value in {"SSC", "HSC", "Dakhil"}
    # a result summary line is always rendered
    assert any("exam(s)" in m.value for m in at.markdown)


@pytest.mark.skipif(not ARCHIVE.exists(), reason="ssc_archive.db not present")
def test_sync_db_target_is_readable_by_the_app():
    """The archive edited by sync_db.py must satisfy what app.py queries."""
    from sync_db import ARCHIVE_DDL  # noqa: F401  (keeps the two schemas linked)

    import sqlite3

    conn = sqlite3.connect(f"file:{ARCHIVE.resolve()}?mode=ro", uri=True)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"board_exams", "exam_questions"} <= tables
    for sql in ("SELECT class_key, subject, board, year FROM board_exams",
                "SELECT exam_id, question_type, question_no, options_json FROM exam_questions"):
        conn.execute(sql).fetchall()
    conn.close()