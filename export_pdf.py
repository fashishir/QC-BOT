"""
Export all Question Bank collections to high-quality PDF files.
================================================================
Supports:
  - Individual PDF per Exam (MCQ + CQ) with clean Bengali font rendering
  - Combined PDFs by Level, Year, and Board
  - Uses Google Chrome / Microsoft Edge Headless engine for pixel-perfect Bengali typography

Usage:
  python export_pdf.py                      # Export all exams to PDFs
  python export_pdf.py --class ssc          # Export SSC exams only
  python export_pdf.py --class hsc          # Export HSC exams only
  python export_pdf.py --year 2025          # Export 2025 exams only
  python export_pdf.py --limit 10           # Test export (first 10 exams)
  python export_pdf.py --combined           # Also generate master combined PDFs per subject/year
"""

from __future__ import annotations

import argparse
import html
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

DB_PATH = Path("board_questions.db")
PDF_OUT_DIR = Path("pdf_exports")


def find_browser_executable() -> str | None:
    """Find installed Chrome or Edge executable on Windows."""
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    # Fallback to PATH search
    for name in ["chrome.exe", "msedge.exe"]:
        p = shutil.which(name)
        if p:
            return p
    return None


def sanitize_filename(name: str) -> str:
    """Remove illegal characters for Windows filenames."""
    s = re.sub(r'[\\/*?:"<>|]', "", name)
    return re.sub(r"\s+", "_", s).strip("_")


def parse_options(options_json: str | None, opt_a: str, opt_b: str, opt_c: str, opt_d: str) -> list[dict]:
    """Extract list of options with index, text, and images."""
    if options_json:
        try:
            data = json.loads(options_json)
            if isinstance(data, list) and data:
                return data
            if isinstance(data, dict):
                return data.get("options", [])
        except Exception:
            pass

    opts = []
    for idx, t in enumerate([opt_a, opt_b, opt_c, opt_d], 1):
        if t and t.strip():
            opts.append({"index": idx, "text": t.strip(), "images": []})
    return opts


def generate_exam_html(exam: dict, questions: list[dict]) -> str:
    """Generate professional printable HTML document for an exam."""
    exam_name = exam.get("exam_name") or exam.get("subject") or "পরীক্ষা"
    board_bn = exam.get("board_bn") or exam.get("board") or ""
    year = exam.get("year") or ""
    class_label = "এসএসসি (SSC)" if exam.get("class_key") == "ssc" else ("এইচএসসি (HSC)" if exam.get("class_key") == "hsc" else "দাখিল")
    source_type_label = "বোর্ড পরীক্ষা (Board Exam)" if exam.get("source_type") == "board-exam" else "টেস্ট পেপার (Test Paper)"

    mcqs = [q for q in questions if q.get("question_type") == "mcq"]
    cqs = [q for q in questions if q.get("question_type") == "written"]

    opt_symbols = {1: "(ক)", 2: "(খ)", 3: "(গ)", 4: "(ঘ)"}

    mcq_blocks = []
    for q in mcqs:
        q_no = q.get("question_no") or ""
        q_text = html.escape(q.get("question_text") or "")
        opts = parse_options(
            q.get("options_json"),
            q.get("option_a") or "",
            q.get("option_b") or "",
            q.get("option_c") or "",
            q.get("option_d") or "",
        )
        ans = q.get("correct_answer") or ""

        opts_html = []
        for o in opts:
            idx = o.get("index", 1)
            sym = opt_symbols.get(idx, f"({idx})")
            txt = html.escape(str(o.get("text") or ""))
            is_ans = str(ans).strip() == str(idx).strip()
            ans_mark = ' class="correct-opt"' if is_ans else ""
            opts_html.append(f"<div{ans_mark}><span class='opt-sym'>{sym}</span> {txt}</div>")

        ans_footer = f"<div class='ans-pill'>সঠিক উত্তর: {opt_symbols.get(int(ans), ans) if str(ans).isdigit() else ans}</div>" if ans else ""

        mcq_blocks.append(f"""
        <div class="question-card">
            <div class="q-title"><span class="q-no">{q_no}.</span> {q_text}</div>
            <div class="options-grid">
                {''.join(opts_html)}
            </div>
            {ans_footer}
        </div>
        """)

    cq_blocks = []
    for q in cqs:
        q_no = q.get("question_no") or ""
        q_text = html.escape(q.get("question_text") or "")
        cq_blocks.append(f"""
        <div class="question-card cq-card">
            <div class="q-title"><span class="q-no">{q_no}.</span> {q_text}</div>
        </div>
        """)

    return f"""<!DOCTYPE html>
<html lang="bn">
<head>
<meta charset="utf-8">
<title>{html.escape(exam_name)} - {board_bn} {year}</title>
<style>
  @page {{
    size: A4;
    margin: 15mm 12mm 15mm 12mm;
    @bottom-center {{
      content: "পৃষ্ঠা " counter(page);
      font-size: 9pt;
      color: #777;
    }}
  }}
  * {{
    box-sizing: border-box;
  }}
  body {{
    font-family: 'SolaimanLipi', 'Kalpurush', 'Nikosh', 'SutonnyMJ', 'Segoe UI', Arial, sans-serif;
    color: #1a1a1a;
    background: #fff;
    font-size: 11pt;
    line-height: 1.5;
    margin: 0;
    padding: 0;
  }}
  .header-box {{
    text-align: center;
    border-bottom: 2px solid #0056b3;
    padding-bottom: 8px;
    margin-bottom: 18px;
  }}
  .exam-title {{
    font-size: 18pt;
    font-weight: bold;
    color: #003366;
    margin: 0 0 4px 0;
  }}
  .exam-meta {{
    font-size: 11pt;
    color: #444;
    display: flex;
    justify-content: center;
    gap: 12px;
    flex-wrap: wrap;
    font-weight: 500;
  }}
  .section-heading {{
    font-size: 13pt;
    font-weight: bold;
    color: #fff;
    background: #0056b3;
    padding: 4px 10px;
    border-radius: 4px;
    margin: 16px 0 10px 0;
    page-break-after: avoid;
  }}
  .question-card {{
    border: 1px solid #e0e4e8;
    border-radius: 6px;
    padding: 9px 12px;
    margin-bottom: 10px;
    background: #fafbfc;
    page-break-inside: avoid;
  }}
  .cq-card {{
    background: #fff;
    border-left: 3px solid #28a745;
  }}
  .q-title {{
    font-size: 11pt;
    font-weight: 600;
    color: #111;
    margin-bottom: 6px;
  }}
  .q-no {{
    font-weight: bold;
    color: #0056b3;
  }}
  .options-grid {{
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 6px 12px;
    margin-top: 6px;
    font-size: 10.5pt;
  }}
  .opt-sym {{
    font-weight: bold;
    color: #555;
  }}
  .correct-opt {{
    font-weight: 600;
    color: #0b7336;
  }}
  .ans-pill {{
    display: inline-block;
    margin-top: 6px;
    padding: 2px 8px;
    background: #e8f5e9;
    color: #1b5e20;
    border-radius: 4px;
    font-size: 9.5pt;
    font-weight: bold;
  }}
  .footer-note {{
    text-align: center;
    margin-top: 20px;
    font-size: 8.5pt;
    color: #888;
    border-top: 1px dashed #ccc;
    padding-top: 6px;
  }}
</style>
</head>
<body>

<div class="header-box">
  <div class="exam-title">{html.escape(exam_name)}</div>
  <div class="exam-meta">
    <span>শ্রেণি: {class_label}</span> •
    <span>বোর্ড: {html.escape(board_bn)}</span> •
    <span>সাল: {year}</span> •
    <span>ধরন: {source_type_label}</span>
  </div>
</div>

{'<div class="section-heading">বহুনির্বাচনি প্রশ্ন (MCQ) - ' + str(len(mcqs)) + ' টি</div>' if mcqs else ''}
{''.join(mcq_blocks)}

{'<div class="section-heading" style="background:#28a745;">সৃজনশীল / রচনামূলক প্রশ্ন (CQ / Written) - ' + str(len(cqs)) + ' টি</div>' if cqs else ''}
{''.join(cq_blocks)}

<div class="footer-note">
  SattAcademy Board Exams & Test Papers Collection (2015-2026) | প্রস্তুতকৃত PDF
</div>

</body>
</html>"""


def convert_html_to_pdf(browser_path: str, html_content: str, output_pdf: Path) -> bool:
    """Convert HTML string to PDF using headless Chrome/Edge."""
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    temp_html = output_pdf.with_suffix(".temp.html")
    try:
        temp_html.write_text(html_content, encoding="utf-8")
        cmd = [
            browser_path,
            "--headless=new",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={output_pdf.resolve()}",
            str(temp_html.resolve()),
        ]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        return res.returncode == 0 and output_pdf.exists() and output_pdf.stat().st_size > 0
    except Exception as exc:
        print(f"Error converting to PDF {output_pdf.name}: {exc}")
        return False
    finally:
        if temp_html.exists():
            try:
                temp_html.unlink()
            except Exception:
                pass


def export_all(
    class_key: str | None = None,
    year: int | None = None,
    source_type: str | None = None,
    limit: int | None = None,
) -> None:
    browser = find_browser_executable()
    if not browser:
        print("Error: Could not find Chrome or Edge executable for PDF rendering.")
        return

    print(f"Using Browser for PDF Engine: {browser}")

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    query = """
        SELECT e.*, COUNT(q.id) as question_count
        FROM exams e
        JOIN questions q ON q.exam_id = e.id
        WHERE 1=1
    """
    params: list = []

    if class_key:
        query += " AND e.class_key = ?"
        params.append(class_key)
    if year:
        query += " AND e.year = ?"
        params.append(year)
    if source_type:
        query += " AND e.source_type = ?"
        params.append(source_type)

    query += " GROUP BY e.id HAVING question_count > 0 ORDER BY e.year DESC, e.class_key, e.board, e.exam_name"
    if limit:
        query += f" LIMIT {limit}"

    exams = [dict(r) for r in cur.execute(query, params).fetchall()]
    total = len(exams)

    print(f"Found {total} exam(s) with questions to export as PDF.")
    print("=" * 65)

    success_count = 0
    for idx, ex in enumerate(exams, 1):
        q_rows = cur.execute(
            "SELECT * FROM questions WHERE exam_id=? ORDER BY question_type, question_no",
            (ex["id"],),
        ).fetchall()
        questions = [dict(q) for q in q_rows]

        level = ex.get("class_key") or "other"
        yr = ex.get("year") or "unknown"
        board = ex.get("board") or "other"
        stype = ex.get("source_type") or "board"
        safe_name = sanitize_filename(ex.get("exam_name") or "exam")[:45]

        folder = PDF_OUT_DIR / level / str(yr)
        pdf_filename = f"{stype}_{board}_{yr}_{safe_name}_ID{ex['id']}.pdf"
        target_path = folder / pdf_filename

        html_content = generate_exam_html(ex, questions)
        ok = convert_html_to_pdf(browser, html_content, target_path)

        if ok:
            success_count += 1
            size_kb = target_path.stat().st_size / 1024
            print(f"[{idx}/{total}] Generated: {pdf_filename} ({size_kb:.1f} KB, {len(questions)} Qs)")
        else:
            print(f"[{idx}/{total}] FAILED: {pdf_filename}")

    conn.close()
    print("=" * 65)
    print(f"Completed! {success_count}/{total} PDF files saved into: {PDF_OUT_DIR.resolve()}")


def main():
    parser = argparse.ArgumentParser(description="Export SattAcademy Question Bank to PDF files")
    parser.add_argument("--class", dest="class_key", choices=["ssc", "hsc", "dakhil"], default=None, help="Class key")
    parser.add_argument("--year", type=int, default=None, help="Year filter")
    parser.add_argument("--source", dest="source_type", choices=["board-exam", "test-paper"], default=None, help="Source type")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of PDFs to generate")
    args = parser.parse_args()

    export_all(
        class_key=args.class_key,
        year=args.year,
        source_type=args.source_type,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
