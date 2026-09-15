"""Tests for duplicate detection."""

from ssc_scraper.config import DatabaseConfig
from ssc_scraper.db import Database
from ssc_scraper.dedupe import DuplicateDetector


def test_metadata_signature_building():
    assert DuplicateDetector.metadata_signature(
        {"board": " Dhaka ", "year": 2023, "subject": "Physics", "paper_type": "MCQ"}
    ) == "dhaka|2023|physics|mcq"
    # incomplete metadata -> no signature
    assert DuplicateDetector.metadata_signature({"board": "dhaka"}) is None


def test_hash_duplicate_detected(tmp_path):
    db = Database(DatabaseConfig(backend="sqlite", sqlite_path=str(tmp_path / "t.db")))
    db.connect()
    db.create_schema()
    detector = DuplicateDetector(db)
    db.upsert_paper({"file_url": "u1", "file_hash": "AA", "status": "downloaded"})

    is_dup, reason = detector.check("AA")
    assert is_dup and "sha256" in reason
    assert detector.check("BB") == (False, "")
    assert detector.check("AA", exclude_id=1) == (False, "")


def test_metadata_signature_duplicate_detected(tmp_path):
    db = Database(DatabaseConfig(backend="sqlite", sqlite_path=str(tmp_path / "t.db")))
    db.connect()
    db.create_schema()
    detector = DuplicateDetector(db)
    db.upsert_paper({"file_url": "u1", "board": "dhaka", "year": 2023,
                     "subject": "physics", "paper_type": "mcq",
                     "file_hash": "AA", "status": "extracted"})

    is_dup, reason = detector.check("BB", record={
        "board": "Dhaka", "year": 2023, "subject": "Physics", "paper_type": "MCQ",
    })
    assert is_dup and "metadata signature" in reason
