"""Tests for sync_db (raw scrape DB -> archive DB used by the Streamlit app)."""

import json
import sqlite3

import pytest

import sync_db

RAW_DDL = """
CREATE TABLE IF NOT EXISTS exams (
    id INTEGER PRIMARY KEY AUTOINCREMENT, remote_id TEXT, class_key TEXT,
    board TEXT, board_bn TEXT, year INTEGER, exam_name TEXT, subject TEXT,
    mcq_url TEXT UNIQUE, written_url TEXT, mcq_count INTEGER, cq_count INTEGER,
    status TEXT DEFAULT 'listed', scraped_at TEXT,
    CONSTRAINT uq_exam UNIQUE (mcq_url)
);
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, exam_id INTEGER REFERENCES exams(id),
    question_no INTEGER, question_type TEXT, question_text TEXT,
    option_a TEXT, option_b TEXT, option_c TEXT, option_d TEXT,
    correct_answer TEXT, options_json TEXT, source_url TEXT, scraped_at TEXT,
    CONSTRAINT uq_q UNIQUE (exam_id, question_type, question_no)
);
"""

MCQ_URL = "https://sattacademy.com/board-exams/dhaka-2015/mcq"
WRITTEN_URL = "https://sattacademy.com/board-exams/dhaka-2015/written"


def make_raw_db(path, *, subject=None, with_written=True):
    """Create a board_questions.db lookalike with one exam and two questions."""
    conn = sqlite3.connect(str(path))
    conn.executescript(RAW_DDL)
    conn.execute(
        "INSERT INTO exams (remote_id, class_key, board, board_bn, year, exam_name,"
        " subject, mcq_url, written_url, mcq_count, cq_count, status, scraped_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("77", "ssc", "dhaka", "ঢাকা বোর্ড", 2015, "বাংলাদেশ ও বিশ্বপরিচয়", subject,
         MCQ_URL, WRITTEN_URL, 40, 45, "completed", "2026-09-16T01:00:00"),
    )
    conn.execute(
        "INSERT INTO questions (exam_id, question_no, question_type, question_text,"
        " option_a, option_b, option_c, option_d, correct_answer, options_json,"
        " source_url, scraped_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (1, 1, "mcq", "টাইটান কোন গ্রহের উপগ্রহ?", "শনি", "বৃহস্পতি", "নেপচুন",
         "ইউরেনাস", "1",
         json.dumps([{"index": 1, "text": "শনি", "images": []}], ensure_ascii=False),
         MCQ_URL + "/q-1", "2026-09-16T01:01:00"),
    )
    if with_written:
        conn.execute(
            "INSERT INTO questions (exam_id, question_no, question_type, question_text,"
            " options_json, source_url, scraped_at) VALUES (?,?,?,?,?,?,?)",
            (1, 1, "written", "যেকোনো পাঁচটি প্রশ্নের উত্তর দাও।", "[]",
             WRITTEN_URL + "/q-55", "2026-09-16T01:02:00"),
        )
    conn.commit()
    conn.close()
    return path


def archive_rows(target, table):
    conn = sqlite3.connect(str(target))
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(f"SELECT * FROM {table}")]
    conn.close()
    return rows
def test_sync_imports_exam_and_questions(tmp_path):
    raw = make_raw_db(tmp_path / "raw.db")
    target = tmp_path / "archive.db"

    stats = sync_db.sync(raw, target)

    assert stats["exams_new"] == 1
    assert stats["questions_new"] == 2
    exams = archive_rows(target, "board_exams")
    assert len(exams) == 1
    exam = exams[0]
    assert exam["class_key"] == "ssc"
    assert exam["board"] == "dhaka"
    assert exam["year"] == 2015
    # site counts win when known; total_questions reflects what was actually stored
    assert exam["mcq_count"] == 40 and exam["cq_count"] == 45
    assert exam["total_questions"] == 2
    assert exam["source_name"] == "sattacademy"
    assert exam["created_at"] and exam["updated_at"]

    questions = archive_rows(target, "exam_questions")
    assert [(q["question_type"], q["question_no"]) for q in questions] == [
        ("mcq", 1), ("written", 1)]
    mcq = next(q for q in questions if q["question_type"] == "mcq")
    # options_json normalised to the dict shape app.py parses
    payload = json.loads(mcq["options_json"])
    assert payload["options"][0]["text"] == "শনি"
    assert payload["images"] == []
    assert mcq["answer"] == "1"
    assert mcq["mcq_url"] == MCQ_URL
    written = next(q for q in questions if q["question_type"] == "written")
    assert written["written_url"] == WRITTEN_URL


def test_sync_is_idempotent(tmp_path):
    raw = make_raw_db(tmp_path / "raw.db")
    target = tmp_path / "archive.db"

    first = sync_db.sync(raw, target)
    second = sync_db.sync(raw, target)

    assert first["exams_new"] == 1 and first["questions_new"] == 2
    assert second["exams_new"] == 0 and second["questions_new"] == 0
    assert second["exams_updated"] == 1 and second["questions_updated"] == 2
    assert len(archive_rows(target, "board_exams")) == 1
    assert len(archive_rows(target, "exam_questions")) == 2


def test_subject_falls_back_to_exam_name(tmp_path):
    raw = make_raw_db(tmp_path / "raw.db", subject=None)

    default_target = tmp_path / "default.db"
    sync_db.sync(raw, default_target)
    assert archive_rows(default_target, "board_exams")[0]["subject"] == "বাংলাদেশ ও বিশ্বপরিচয়"

    strict_target = tmp_path / "strict.db"
    sync_db.sync(raw, strict_target, subject_from_name=False)
    assert archive_rows(strict_target, "board_exams")[0]["subject"] is None


def test_counts_fall_back_to_stored_questions(tmp_path):
    """mcq_count/cq_count NULL in the raw DB -> use the stored question counts."""
    raw = make_raw_db(tmp_path / "raw.db")
    conn = sqlite3.connect(str(raw))
    conn.execute("UPDATE exams SET mcq_count=NULL, cq_count=NULL")
    conn.commit()
    conn.close()
    target = tmp_path / "archive.db"

    sync_db.sync(raw, target)

    exam = archive_rows(target, "board_exams")[0]
    assert exam["mcq_count"] == 1
    assert exam["cq_count"] == 1


def test_dry_run_writes_nothing(tmp_path):
    raw = make_raw_db(tmp_path / "raw.db")
    target = tmp_path / "archive.db"

    stats = sync_db.sync(raw, target, dry_run=True)

    assert stats["exams_new"] == 1 and stats["questions_new"] == 2
    assert archive_rows(target, "board_exams") == []
    assert archive_rows(target, "exam_questions") == []


def test_missing_source_db_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        sync_db.sync(tmp_path / "nope.db", tmp_path / "archive.db")


def test_normalise_options_accepts_dict_and_list():
    as_list = sync_db.normalise_options(json.dumps([{"index": 1, "text": "ক"}]))
    assert json.loads(as_list) == {"options": [{"index": 1, "text": "ক"}], "images": []}

    as_dict = sync_db.normalise_options('{"options": [{"index": 1}], "images": ["u"]}')
    assert json.loads(as_dict) == {"options": [{"index": 1}], "images": ["u"]}

    assert sync_db.normalise_options(None) == '{"options": [], "images": []}'
    assert sync_db.normalise_options("not json") == '{"options": [], "images": []}'