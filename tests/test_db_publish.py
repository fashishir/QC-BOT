"""Database constraints, upserts, and publish-gate tests."""

import sqlite3

import pytest

from job_scraper.db import Database, publish_archive


def make_db(path):
    return Database(path).initialize()


def add_exam(db, source, source_id, name, year=2025, coverage="fallback_15"):
    return db.upsert_exam({
        "source": source,
        "source_id": source_id,
        "exam_name": name,
        "institution": "টেস্ট প্রতিষ্ঠান",
        "exam_date": f"{year}-09-19",
        "year": year,
        "exam_type": "mcq",
        "total_questions": 2,
        "coverage_status": coverage,
        "is_partial": 1,
        "partial_reason": "public_page_limit",
        "source_url": "https://example.test/exam",
        "status": "published",
    })


def add_questions(db, exam_id):
    db.replace_questions(exam_id, [
        {
            "question_no": 1, "question_text": "প্রশ্ন এক?",
            "options": ["ক", "খ", "গ", "ঘ"], "answer_index": 2,
            "answer_source": "sattacademy",
        },
        {
            "question_no": 2, "question_text": "প্রশ্ন দুই?",
            "options": ["ক", "খ", "গ", "ঘ"], "answer_index": None,
            "answer_source": "sattacademy",
        },
    ])


def test_upsert_is_idempotent_and_recounts(tmp_path):
    db = make_db(tmp_path / "raw.db")
    cat_id = db.upsert_category("bcs", "বিসিএস প্রিলিমিনারি", 1, "https://example.test/cat")
    exam_id = add_exam(db, "sattacademy", "101", "বিসিএস ২০২৫")
    db.set_exam_categories(exam_id, [cat_id])
    add_questions(db, exam_id)

    same_id = add_exam(db, "sattacademy", "101", "বিসিএস ২০২৫ (আপডেট)")
    assert same_id == exam_id
    assert db.stats()["exams"] == 1
    assert db.stats()["questions"] == 2
    assert db.stats()["answered"] == 1
    row = db.get_exam(exam_id)
    assert row["exam_name"].endswith("(আপডেট)")
    assert row["collected_questions"] == 2
    assert row["answered_questions"] == 1


def test_year_constraint_rejects_out_of_range(tmp_path):
    db = make_db(tmp_path / "raw.db")
    with pytest.raises(sqlite3.IntegrityError):
        add_exam(db, "sattacademy", "old", "পুরনো পরীক্ষা", year=2024)


def test_answer_index_constraint_and_missing_status(tmp_path):
    db = make_db(tmp_path / "raw.db")
    exam_id = add_exam(db, "sattacademy", "101", "বিসিএস")
    add_questions(db, exam_id)
    rows = db.get_questions(exam_id)
    assert rows[0]["answer_index"] == 2
    assert rows[0]["answer_status"] == "published"
    assert rows[1]["answer_index"] is None
    assert rows[1]["answer_status"] == "missing"
    assert rows[0]["explanation"] is None


def test_publish_gates_third_party_and_review_rows(tmp_path):
    raw_path = tmp_path / "raw.db"
    archive_path = tmp_path / "archive.db"
    db = make_db(raw_path)
    cat_id = db.upsert_category("bcs", "বিসিএস", 1)
    satta_id = add_exam(db, "sattacademy", "101", "সাততা পরীক্ষা")
    db.set_exam_categories(satta_id, [cat_id])
    add_questions(db, satta_id)
    # one needs-review row must be excluded
    db.replace_questions(satta_id, [
        {"question_no": 1, "question_text": "ভালো প্রশ্ন?",
         "options": ["ক", "খ", "গ", "ঘ"], "answer_index": 1},
        {"question_no": 2, "question_text": "সমস্যাযুক্ত?",
         "options": ["ক", "খ"], "answer_index": None,
         "review_status": "needs_review"},
    ])

    lm_id = add_exam(db, "livemcq", "47th", "লাইভ পরীক্ষা", coverage="partial_pdf")
    db.set_exam_categories(lm_id, [cat_id])
    db.replace_questions(lm_id, [
        {"question_no": 1, "question_text": "লাইভ প্রশ্ন?",
         "options": ["ক", "খ", "গ", "ঘ"], "answer_index": 2,
         "answer_source": "livemcq"},
    ])
    # no document yet -> excluded
    stats = publish_archive(raw_path, archive_path)
    assert stats["exams"] == 1

    db.record_document(
        lm_id, doc_type="solution_page", source_name="Live MCQ",
        source_url="https://web.livemcq.com/blog/x", license_status="approved",
        publish_allowed=True, permission_note="approved for project",
    )
    stats = publish_archive(raw_path, archive_path)
    assert stats["exams"] == 2
    assert stats["questions"] == 2
    assert stats["answered"] == 2

    out = sqlite3.connect(archive_path)
    assert out.execute("SELECT COUNT(*) FROM job_questions WHERE review_status='needs_review'").fetchone()[0] == 0
    assert out.execute("SELECT COUNT(*) FROM job_questions WHERE explanation IS NOT NULL").fetchone()[0] == 0
    out.close()


def test_publish_refuses_empty_archive(tmp_path):
    raw_path = tmp_path / "raw.db"
    make_db(raw_path).close()
    with pytest.raises(ValueError):
        publish_archive(raw_path, tmp_path / "archive.db")
