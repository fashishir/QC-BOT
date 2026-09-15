"""Tests for report generation."""

from ssc_scraper.config import DatabaseConfig, Settings
from ssc_scraper.db import Database
from ssc_scraper.reports import ReportGenerator


def make_env(tmp_path):
    db = Database(DatabaseConfig(backend="sqlite", sqlite_path=str(tmp_path / "t.db")))
    db.connect()
    db.create_schema()
    settings = Settings(reports_dir=str(tmp_path / "reports"), storage_root=str(tmp_path))
    return db, ReportGenerator(db, settings)


def test_dashboard_totals(tmp_path):
    db, generator = make_env(tmp_path)
    db.upsert_paper({"file_url": "u1", "board": "dhaka", "year": 2023,
                     "subject": "physics", "status": "downloaded"})
    db.upsert_paper({"file_url": "u2", "status": "failed"})
    dashboard = generator.build_dashboard()
    assert dashboard["totals"]["files_found"] == 2
    assert dashboard["totals"]["files_downloaded"] == 1
    assert dashboard["totals"]["failed"] == 1
    assert "2023" not in dashboard["missing"]["years"]


def test_missing_report_files_written(tmp_path):
    db, generator = make_env(tmp_path)
    db.upsert_paper({"file_url": "u1", "board": "dhaka", "year": 2023,
                     "subject": "physics", "status": "extracted"})
    csv_path = generator.write_missing_report()
    json_path = csv_path.with_suffix(".json")
    assert csv_path.exists() and json_path.exists()
    missing = generator.missing_combinations()
    # the collected combo must not appear in the missing list
    assert {"board": "dhaka", "year": 2023, "subject": "physics"} not in missing
    # but most combinations are missing (2005-2026 grid)
    assert len(missing) > 4000


def test_export_csv(tmp_path):
    db, generator = make_env(tmp_path)
    db.upsert_paper({"file_url": "u1", "board": "dhaka", "year": 2023,
                     "subject": "physics", "status": "downloaded",
                     "ocr_text": "long text should be excluded"})
    out = generator.export_papers_csv(str(tmp_path / "export.csv"))
    content = out.read_text(encoding="utf-8")
    assert "u1" in content and "long text should be excluded" not in content
