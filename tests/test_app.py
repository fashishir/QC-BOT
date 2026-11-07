"""Streamlit smoke test: the app renders the published archive."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
ARCHIVE = ROOT / "job_archive.db"


@pytest.mark.skipif(not ARCHIVE.exists(), reason="job_archive.db not built yet")
def test_app_renders_job_question_bank():
    at = AppTest.from_file(str(APP), default_timeout=180).run()
    assert not at.exception, [f"{e.type}: {e.message}" for e in at.exception]
    assert any("চাকরি পরীক্ষার MCQ প্রশ্নব্যাংক" in m.value for m in at.markdown)
    labels = [s.label for s in at.selectbox] + [s.label for s in at.multiselect]
    assert "বছর" in labels
    assert "বিভাগ" in labels


@pytest.mark.skipif(not ARCHIVE.exists(), reason="job_archive.db not built yet")
def test_archive_has_only_2025_2026_rows():
    import sqlite3

    conn = sqlite3.connect(f"file:{ARCHIVE.resolve()}?mode=ro", uri=True)
    years = {row[0] for row in conn.execute("SELECT DISTINCT year FROM job_exams")}
    assert years <= {2025, 2026}
    bad = conn.execute(
        "SELECT COUNT(*) FROM job_questions WHERE explanation IS NOT NULL"
    ).fetchone()[0]
    assert bad == 0
    conn.close()
