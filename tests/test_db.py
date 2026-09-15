"""Tests for the storage layer (SQLite)."""

from ssc_scraper.config import DatabaseConfig
from ssc_scraper.db import Database


def make_db(tmp_path):
    db = Database(DatabaseConfig(backend="sqlite",
                                 sqlite_path=str(tmp_path / "t.db")))
    db.connect()
    db.create_schema()
    return db


def test_upsert_and_fetch_paper(tmp_path):
    db = make_db(tmp_path)
    paper_id = db.upsert_paper({
        "file_url": "https://example.org/a.pdf",
        "board": "dhaka", "year": 2023, "subject": "physics",
        "status": "downloaded", "file_hash": "abc123",
    })
    row = db.get_paper_by_url("https://example.org/a.pdf")
    assert row["id"] == paper_id
    assert row["board"] == "dhaka"

    # Upserting the same URL updates instead of duplicating
    db.upsert_paper({"file_url": "https://example.org/a.pdf", "status": "extracted"})
    assert db.get_paper_by_url("https://example.org/a.pdf")["status"] == "extracted"
    assert len(db.iter_papers()) == 1


def test_invalid_status_rejected(tmp_path):
    db = make_db(tmp_path)
    try:
        db.upsert_paper({"file_url": "x", "status": "bogus"})
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_hash_lookup_with_exclusion(tmp_path):
    db = make_db(tmp_path)
    first = db.upsert_paper({"file_url": "u1", "file_hash": "H", "status": "downloaded"})
    second = db.upsert_paper({"file_url": "u2", "file_hash": "H", "status": "downloaded"})
    assert db.get_paper_by_hash("H", exclude_id=second)["id"] == first
    assert db.get_paper_by_hash("missing") is None


def test_crawl_state_upsert(tmp_path):
    db = make_db(tmp_path)
    db.set_crawl_state("https://a/1", "src", "pending", depth=0)
    db.set_crawl_state("https://a/1", "src", "visited", depth=1, context="t")
    state = db.get_crawl_state("https://a/1")
    assert state["status"] == "visited"
    assert state["depth"] == 1
    assert state["context"] == "t"
    assert db.count_crawl("src", "visited") == 1


def test_signature_lookup(tmp_path):
    db = make_db(tmp_path)
    db.upsert_paper({"file_url": "u1", "board": "Dhaka", "year": 2023,
                     "subject": "Physics", "paper_type": "MCQ",
                     "status": "downloaded"})
    found = db.get_paper_by_signature({"board": "dhaka", "year": 2023,
                                       "subject": "physics", "paper_type": "mcq"})
    assert found is not None
    assert db.get_paper_by_signature({"board": "khulna", "year": 2023,
                                      "subject": "physics", "paper_type": "mcq"}) is None


def test_source_status_manual_review(tmp_path):
    db = make_db(tmp_path)
    db.upsert_source("s1", "https://s1.example", True)
    db.set_source_status("s1", "manual_review", note="HTTP 403")
    # no getter needed; just ensure no crash and second note appends
    db.set_source_status("s1", "manual_review", note="again")


def test_count_by_status_and_field(tmp_path):
    db = make_db(tmp_path)
    db.upsert_paper({"file_url": "u1", "board": "dhaka", "year": 2023,
                     "subject": "physics", "status": "downloaded"})
    db.upsert_paper({"file_url": "u2", "board": "dhaka", "year": 2023,
                     "subject": "chemistry", "status": "failed"})
    counts = db.count_by_status()
    assert counts["downloaded"] == 1 and counts["failed"] == 1
    per_subject = db.count_by_field("subject")
    assert per_subject == {"physics": 1}  # failed rows excluded
    combos = db.distinct_combos()
    assert combos == [("dhaka", 2023, "physics")]
