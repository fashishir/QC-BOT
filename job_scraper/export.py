"""CSV / print-HTML / PDF export for the job-exam archive.

Reads only ``job_archive.db``. Every export carries exam metadata, coverage
status, and source attribution. Explanations are never exported (v1).
"""

from __future__ import annotations

import csv
import html
import json
import logging
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)

OPTION_SYMBOLS = {1: "(ক)", 2: "(খ)", 3: "(গ)", 4: "(ঘ)"}
COVERAGE_LABELS = {
    "full": "পূর্ণ",
    "partial_pdf": "আংশিক",
    "fallback_15": "ফলব্যাক ১৫",
    "missing": "অনুপলব্ধ",
}


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def source_label(conn: sqlite3.Connection, exam_id: int) -> str:
    row = conn.execute(
        "SELECT source_name FROM job_documents WHERE exam_id=? AND publish_allowed=1 "
        "ORDER BY CASE source_name WHEN 'Live MCQ' THEN 0 ELSE 1 END LIMIT 1",
        (exam_id,),
    ).fetchone()
    return row["source_name"] if row else "SattAcademy"


def list_exams(db_path: str | Path, *, exam_id: int | None = None,
               category: str | None = None, year: int | None = None,
               limit: int | None = None) -> list[dict]:
    conn = connect(db_path)
    sql = [
        """
        SELECT e.*, GROUP_CONCAT(DISTINCT c.name) AS category_names
        FROM job_exams e
        LEFT JOIN job_exam_categories ec ON ec.exam_id = e.id
        LEFT JOIN job_categories c ON c.id = ec.category_id
        WHERE 1=1
        """
    ]
    params: list = []
    if exam_id is not None:
        sql.append("AND e.id = ?")
        params.append(exam_id)
    if category:
        sql.append("AND c.name = ?")
        params.append(category)
    if year:
        sql.append("AND e.year = ?")
        params.append(year)
    sql.append("GROUP BY e.id ORDER BY e.exam_date DESC, e.exam_name")
    if limit:
        sql.append("LIMIT ?")
        params.append(limit)
    rows = [dict(r) for r in conn.execute(" ".join(sql), params).fetchall()]
    for row in rows:
        row["source_label"] = source_label(conn, row["id"])
        row["coverage_label"] = COVERAGE_LABELS.get(row["coverage_status"], row["coverage_status"])
    conn.close()
    return rows


def get_questions(db_path: str | Path, exam_id: int) -> list[dict]:
    conn = connect(db_path)
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM job_questions WHERE exam_id=? ORDER BY question_no", (exam_id,)
    ).fetchall()]
    conn.close()
    return rows


def _options(row: dict) -> list[str]:
    return [row.get(f"option_{i}") or "" for i in range(1, 5)]


def build_print_html(exam: dict, questions: list[dict], *,
                     with_answers: bool = True, practice: bool = False) -> str:
    """Build a Bengali-aware printable HTML document for one exam."""
    title = html.escape(exam.get("exam_name") or "চাকরি পরীক্ষা")
    date = html.escape(str(exam.get("exam_date") or ""))
    source = html.escape(exam.get("source_label") or "SattAcademy")
    coverage = html.escape(exam.get("coverage_label") or "")
    collected = exam.get("collected_questions") or len(questions)
    expected = exam.get("total_questions") or collected
    partial_note = ""
    if exam.get("coverage_status") != "full":
        partial_note = (
            f"<div class='notice'>এই পরীক্ষার সম্পূর্ণ প্রশ্নপত্র পাওয়া যায়নি; "
            f"{collected}/{expected}টি প্রশ্ন সংগ্রহ করা হয়েছে।</div>"
        )

    parts = [
        "<!DOCTYPE html><html lang='bn'><head><meta charset='utf-8'>",
        "<style>",
        "@font-face { font-family: 'Noto Sans Bengali'; src: url('assets/fonts/NotoSansBengali-Regular.ttf'); }",
        "body { font-family: 'Noto Sans Bengali', 'Nirmala UI', sans-serif; font-size: 11pt;",
        "       line-height: 1.65; margin: 16mm 13mm; color: #172033; }",
        "h1 { font-size: 17pt; color: #0b3b6f; border-bottom: 2px solid #0b6bcb;",
        "     padding-bottom: 6px; margin: 0 0 8px; }",
        ".meta { font-size: 9.8pt; color: #4b5563; margin-bottom: 8px; }",
        ".notice { background: #fff7e6; border-left: 4px solid #d97706; padding: 7px 10px;",
        "          font-size: 9.8pt; margin: 8px 0 14px; border-radius: 4px; }",
        ".question { border: 1px solid #e5e7eb; border-radius: 6px; padding: 9px 12px;",
        "            margin-bottom: 9px; page-break-inside: avoid; background: #fbfcfe; }",
        ".q-title { font-weight: 600; margin-bottom: 5px; }",
        ".q-no { color: #0b6bcb; font-weight: 700; }",
        ".options { display: grid; grid-template-columns: 1fr 1fr; gap: 3px 14px;",
        "           font-size: 10.4pt; margin-top: 4px; }",
        ".correct { color: #0b7336; font-weight: 700; }",
        ".answer { display: inline-block; margin-top: 6px; padding: 2px 9px;",
        "          background: #e8f5e9; color: #14532d; border-radius: 4px;",
        "          font-size: 9.5pt; font-weight: 700; }",
        ".missing { background: #f3f4f6; color: #6b7280; }",
        ".source { margin-top: 18px; font-size: 9pt; color: #4b5563; border-top: 1px solid #e5e7eb;",
        "          padding-top: 8px; }",
        "@page { size: A4; margin: 12mm; }",
        "</style></head><body>",
        f"<h1>{title}</h1>",
        f"<div class='meta'>পরীক্ষার তারিখ: {date or '—'} · কভারেজ: {coverage} · "
        f"প্রশ্ন: {collected}/{expected} · উৎস: {source}</div>",
        partial_note,
    ]

    for q in questions:
        q_no = html.escape(str(q.get("question_no") or ""))
        q_text = html.escape(q.get("question_text") or "")
        options = _options(q)
        answer = q.get("answer_index")
        option_html = []
        for idx, text in enumerate(options, start=1):
            symbol = OPTION_SYMBOLS[idx]
            is_correct = with_answers and answer == idx and not practice
            css = " class='correct'" if is_correct else ""
            option_html.append(f"<div{css}>{symbol} {html.escape(text)}</div>")
        footer = ""
        if with_answers and not practice:
            if answer in (1, 2, 3, 4):
                footer = f"<div class='answer'>সঠিক উত্তর: {OPTION_SYMBOLS[answer]}</div>"
            else:
                footer = "<div class='answer missing'>উত্তর প্রকাশিত হয়নি</div>"
        parts.append(
            f"<div class='question'><div class='q-title'>"
            f"<span class='q-no'>{q_no}.</span> {q_text}</div>"
            f"<div class='options'>{''.join(option_html)}</div>{footer}</div>"
        )

    parts.append(
        f"<div class='source'>উৎস: {source} — "
        f"<a href='{html.escape(exam.get('source_url') or '')}'>"
        f"{html.escape(exam.get('source_url') or '')}</a><br>"
        "সংকলন: চাকরি পরীক্ষার MCQ প্রশ্নব্যাংক (২০২৫–২০২৬)</div>"
    )
    parts.append("</body></html>")
    return "".join(parts)


def html_to_pdf(html_content: str) -> bytes | None:
    try:
        from weasyprint import HTML as WeasyHTML

        pdf = WeasyHTML(string=html_content, base_url=".").write_pdf()
        return bytes(pdf) if pdf else None
    except Exception as exc:  # missing Pango/system libs, import errors, ...
        log.warning("WeasyPrint PDF render failed: %s", exc)
        return None


def export_csv(db_path: str | Path, output: str | Path, *,
               exam_id: int | None = None, category: str | None = None,
               year: int | None = None, limit: int | None = None) -> int:
    exams = list_exams(db_path, exam_id=exam_id, category=category, year=year, limit=limit)
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with out.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "exam_id", "exam_name", "exam_date", "year", "category",
            "coverage_status", "total_questions", "collected_questions",
            "source", "source_url", "question_no", "question_text",
            "option_1", "option_2", "option_3", "option_4",
            "answer_index", "answer_text", "answer_status",
        ])
        for exam in exams:
            for q in get_questions(db_path, exam["id"]):
                writer.writerow([
                    exam["id"], exam["exam_name"], exam["exam_date"], exam["year"],
                    exam.get("category_names") or "", exam["coverage_status"],
                    exam.get("total_questions"), exam.get("collected_questions"),
                    exam.get("source_label"), exam.get("source_url"),
                    q["question_no"], q["question_text"],
                    q["option_1"], q["option_2"], q["option_3"], q["option_4"],
                    q["answer_index"], q["answer_text"], q["answer_status"],
                ])
                count += 1
    return count


def export_pdf_files(db_path: str | Path, output_dir: str | Path, *,
                     exam_id: int | None = None, category: str | None = None,
                     year: int | None = None, with_answers: bool = True,
                     practice: bool = False, limit: int | None = None) -> list[Path]:
    exams = list_exams(db_path, exam_id=exam_id, category=category, year=year, limit=limit)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for exam in exams:
        questions = get_questions(db_path, exam["id"])
        document = build_print_html(exam, questions, with_answers=with_answers, practice=practice)
        pdf_bytes = html_to_pdf(document)
        safe = "".join(c if c.isalnum() else "_" for c in exam["exam_name"])[:70]
        if pdf_bytes:
            path = out_dir / f"{exam['exam_date'] or exam['year']}_{safe}.pdf"
            path.write_bytes(pdf_bytes)
            written.append(path)
        else:
            path = out_dir / f"{exam['exam_date'] or exam['year']}_{safe}.html"
            path.write_text(document, encoding="utf-8")
            written.append(path)
    return written
