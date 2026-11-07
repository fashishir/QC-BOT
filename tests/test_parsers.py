"""Parser tests for SattAcademy job pages and Live MCQ solution pages."""

from pathlib import Path

from job_scraper.livemcq import parse_solution_page
from job_scraper.sattacademy_jobs import (
    has_more_pages,
    parse_category,
    parse_exam_questions,
    parse_hub,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_hub_discovers_job_categories_and_skips_non_job_links():
    categories = parse_hub(_read("job_hub.html"))
    names = [c["name"] for c in categories]
    assert names == ["বিসিএস প্রিলিমিনারি", "বাংলাদেশ ব্যাংক", "শিক্ষক নিবন্ধন ও প্রত্যয়ন পরীক্ষা"]
    assert all(c["slug"] not in {"mcq", "written"} for c in categories)
    assert [c["display_order"] for c in categories] == [1, 2, 3]


def test_category_dedupes_cards_and_filters_to_2025_2026():
    exams = parse_category(_read("job_category.html"), "https://sattacademy.com/job-solution/bcs")
    assert [e["subcat_id"] for e in exams] == ["101", "103"]
    assert exams[0]["exam_date"] == "2025-09-19"
    assert exams[0]["total_questions"] == 200
    assert exams[1]["year"] == 2026
    assert has_more_pages(_read("job_category.html")) is True


def test_exam_page_parses_leaf_cards_only_and_marks_missing_answer():
    questions = parse_exam_questions(
        _read("job_exam.html"), "https://sattacademy.com/47-bcs/all/mcq-questions"
    )
    assert len(questions) == 2
    first, second = questions
    assert first["question_no"] == 1
    assert first["question_text"].startswith("‘ন ক্ষু দা চ’")
    assert first["options"] == ["খুন করা", "খাদ্য গ্রহণ করা", "পলায়ন করা", "চুরি করা"]
    assert first["answer_index"] == 3
    assert first["answer_source"] == "sattacademy"
    assert first["review_status"] == "auto"
    assert second["answer_index"] is None
    assert second["review_status"] == "auto"


def test_livemcq_parser_extracts_answers_and_discards_explanations():
    parsed = parse_solution_page(
        _read("livemcq_solution.html"),
        "https://web.livemcq.com/blog/47th-bcs-question-solution-pdf",
    )
    assert parsed["title"].startswith("৪৭তম বিসিএস")
    questions = parsed["questions"]
    assert len(questions) == 2
    assert questions[0]["question_no"] == 1
    assert questions[0]["answer_index"] == 3
    assert questions[0]["options"] == ["বলে", "ভাবে", "চায়", "দেখে"]
    assert questions[0]["review_status"] == "auto"
    assert questions[1]["answer_index"] == 1  # answer-note fallback
    assert all("ব্যাখ্যা" not in q["question_text"] for q in questions)
    assert "explanation" not in questions[0]
