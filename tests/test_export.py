"""CSV/print export tests."""

import csv
import sqlite3

from job_scraper.db import Database, publish_archive
from job_scraper.export import build_print_html, export_csv, list_exams


def _build_archive(tmp_path):
    raw_path = tmp_path / "raw.db"
    archive_path = tmp_path / "archive.db"
    db = Database(raw_path).initialize()
    cat_id = db.upsert_category("bcs", "বিসিএস প্রিলিমিনারি", 1)
    exam_id = db.upsert_exam({
        "source": "sattacademy", "source_id": "101",
        "exam_name": "৪৭তম বিসিএস প্রিলিমিনারি",
        "exam_date": "2025-09-19", "year": 2025, "exam_type": "mcq",
        "total_questions": 200, "coverage_status": "fallback_15",
        "is_partial": 1, "partial_reason": "public_page_limit",
        "source_url": "https://sattacademy.com/exam", "status": "published",
    })
    db.set_exam_categories(exam_id, [cat_id])
    db.replace_questions(exam_id, [
        {"question_no": 1, "question_text": "প্রশ্ন এক?",
         "options": ["ক", "খ", "গ", "ঘ"], "answer_index": 2},
        {"question_no": 2, "question_text": "প্রশ্ন দুই?",
         "options": ["ক", "খ", "গ", "ঘ"], "answer_index": None},
    ])
    db.close()
    publish_archive(raw_path, archive_path)
    return archive_path


def test_list_exams_includes_source_and_coverage(tmp_path):
    archive = _build_archive(tmp_path)
    exams = list_exams(archive)
    assert len(exams) == 1
    assert exams[0]["source_label"] == "SattAcademy"
    assert exams[0]["coverage_label"] == "ফলব্যাক ১৫"


def test_print_html_contains_answers_and_partial_notice(tmp_path):
    archive = _build_archive(tmp_path)
    exam = list_exams(archive)[0]
    from job_scraper.export import get_questions
    questions = get_questions(archive, exam["id"])
    document = build_print_html(exam, questions, with_answers=True)
    assert "সঠিক উত্তর" in document
    assert "উত্তর প্রকাশিত হয়নি" in document
    assert "সম্পূর্ণ প্রশ্নপত্র পাওয়া যায়নি" in document
    assert "SattAcademy" in document
    assert "ব্যাখ্যা" not in document


def test_csv_export_rows_and_columns(tmp_path):
    archive = _build_archive(tmp_path)
    out = tmp_path / "questions.csv"
    count = export_csv(archive, out)
    assert count == 2
    with out.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    assert rows[0]["answer_index"] == "2"
    assert rows[1]["answer_status"] == "missing"
    assert rows[0]["source"] == "SattAcademy"
    assert "question_text" in rows[0]
