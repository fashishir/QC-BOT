"""Server-side HTML -> PDF export (WeasyPrint) with HTML fallback.

Pure helpers (no Streamlit dependency) so they can be unit-tested and
reused by both ``app.py`` (on-demand download button) and batch scripts.

WeasyPrint gives proper Bengali complex-text shaping via Pango/HarfBuzz,
which reportlab/fpdf cannot do. System deps live in ``packages.txt``;
the Python dep lives in ``requirements.txt`` / ``pyproject.toml``.
"""

from __future__ import annotations

import html
import json
import logging
from collections.abc import Callable

log = logging.getLogger(__name__)


def html_to_pdf(html_content: str) -> bytes | None:
    """Convert an HTML string to PDF bytes using WeasyPrint.

    Returns None if WeasyPrint is unavailable or rendering fails
    (e.g. missing system libs on Streamlit Cloud), letting the caller
    fall back to serving raw HTML.
    """
    try:
        from weasyprint import HTML as WeasyHTML

        pdf = WeasyHTML(string=html_content).write_pdf()
        return bytes(pdf) if pdf else None
    except Exception as exc:  # broad: OSError for missing Pango, ImportError, etc.
        log.warning("WeasyPrint PDF render failed, falling back to HTML: %s", exc)
        return None


def _parse_options(row: dict):
    try:
        data = json.loads(row.get("options_json") or "[]")
    except (TypeError, ValueError):
        return [], [], {}
    if isinstance(data, list):
        # Format: [{"index": 1, "text": "...", "images": [...]}]
        return data, [], {}
    return data.get("options", []), data.get("images", []), data


def build_print_html(exam: dict, questions: list[dict]) -> str:
    """Build the printable HTML document for one exam (Bengali-aware)."""
    title = html.escape(exam.get("exam_name") or exam.get("subject") or "Board Exam")
    board = html.escape(str(exam.get("board") or ""))
    year = html.escape(str(exam.get("year") or ""))
    parts = [
        "<!DOCTYPE html><html lang='bn'><head><meta charset='utf-8'>",
        "<style>",
        "body { font-family: 'Noto Sans Bengali', 'Nirmala UI', 'Vrinda', sans-serif;",
        "       font-size: 11pt; line-height: 1.6; margin: 20mm; color: #1a1a1a; }",
        "h1 { font-size: 16pt; color: #003366; border-bottom: 2px solid #0056b3;",
        "     padding-bottom: 6px; margin-bottom: 12px; }",
        ".meta { font-size: 10pt; color: #555; margin-bottom: 16px; }",
        ".question-card { border: 1px solid #e0e4e8; border-radius: 6px;",
        "                 padding: 10px 14px; margin-bottom: 10px; background: #fafbfc;",
        "                 page-break-inside: avoid; }",
        ".q-title { font-weight: 600; color: #111; margin-bottom: 6px; }",
        ".q-no { font-weight: bold; color: #0056b3; }",
        ".options-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 12px;",
        "                margin-top: 6px; font-size: 10.5pt; }",
        ".correct-opt { font-weight: 600; color: #0b7336; }",
        ".ans-pill { display: inline-block; margin-top: 6px; padding: 2px 8px;",
        "            background: #e8f5e9; color: #1b5e20; border-radius: 4px;",
        "            font-size: 9.5pt; font-weight: bold; }",
        ".cq-card { border-left: 3px solid #28a745; }",
        ".section-heading { font-size: 13pt; font-weight: bold; color: #fff;",
        "                   background: #0056b3; padding: 4px 10px; border-radius: 4px;",
        "                   margin: 16px 0 10px 0; }",
        "@page { size: A4; margin: 15mm 12mm; }",
        "</style></head><body>",
        f"<h1>{title}</h1>",
        f"<div class='meta'>{board} বোর্ড | {year} | উৎস: {html.escape(exam.get('mcq_url') or '')}</div>",
    ]

    opt_symbols = {1: "(ক)", 2: "(খ)", 3: "(গ)", 4: "(ঘ)"}
    mcqs = [q for q in questions if q.get("question_type") == "mcq"]
    cqs = [q for q in questions if q.get("question_type") == "written"]

    if mcqs:
        parts.append("<div class='section-heading'>বহুনির্বাচনি প্রশ্ন (MCQ)</div>")
        for q in mcqs:
            opts, _imgs, _meta = _parse_options(q)
            q_no = q.get("question_no") or ""
            q_text = html.escape(q.get("question_text") or "")
            ans = q.get("correct_answer") or q.get("answer") or ""

            opts_html = []
            for o in opts:
                if isinstance(o, dict):
                    idx = o.get("index", 1)
                    sym = opt_symbols.get(idx, f"({idx})")
                    txt = html.escape(str(o.get("text") or ""))
                    is_ans = str(ans).strip() == str(idx).strip()
                    cls = " class='correct-opt'" if is_ans else ""
                    opts_html.append(f"<div{cls}>{sym} {txt}</div>")

            ans_footer = ""
            if ans:
                ans_sym = opt_symbols.get(int(ans), ans) if str(ans).isdigit() else ans
                ans_footer = f"<div class='ans-pill'>সঠিক উত্তর: {ans_sym}</div>"

            parts.append(
                f"<div class='question-card'>"
                f"<div class='q-title'><span class='q-no'>{q_no}.</span> {q_text}</div>"
                f"<div class='options-grid'>{''.join(opts_html)}</div>"
                f"{ans_footer}</div>"
            )

    if cqs:
        parts.append("<div class='section-heading'>সৃজনশীল প্রশ্ন (CQ)</div>")
        for q in cqs:
            q_no = q.get("question_no") or ""
            q_text = html.escape(q.get("question_text") or "")
            parts.append(
                f"<div class='question-card cq-card'>"
                f"<div class='q-title'><span class='q-no'>{q_no}.</span> {q_text}</div>"
                f"</div>"
            )

    parts.append("</body></html>")
    return "".join(parts)


def export_filename(exam: dict, ext: str) -> str:
    """Build a filesystem-safe download name like ``dhaka_2023_42.pdf``."""
    safe_board = "".join(c if c.isalnum() else "_" for c in str(exam.get("board") or "exam"))
    safe_year = "".join(c if c.isalnum() else "_" for c in str(exam.get("year") or ""))
    exam_id = exam.get("id", "export")
    return f"{safe_board}_{safe_year}_{exam_id}.{ext.lstrip('.')}"


def build_export_payload(
    exam: dict,
    questions: list[dict],
    pdf_converter: Callable[[str], bytes | None] | None = None,
) -> dict:
    """Return download-button payload: PDF bytes when possible, else HTML.

    Returns dict with keys: data (bytes), file_name, mime, label, is_pdf.
    ``pdf_converter`` is injectable for tests; defaults to :func:`html_to_pdf`.
    """
    converter = pdf_converter or html_to_pdf
    print_html = build_print_html(exam, questions)
    try:
        pdf_bytes = converter(print_html)
    except Exception as exc:  # a custom converter may raise instead of returning None
        log.warning("PDF converter raised, falling back to HTML: %s", exc)
        pdf_bytes = None
    if pdf_bytes:
        return {
            "data": bytes(pdf_bytes),
            "file_name": export_filename(exam, "pdf"),
            "mime": "application/pdf",
            "label": "⬇ Download PDF",
            "is_pdf": True,
        }
    return {
        "data": print_html.encode("utf-8"),
        "file_name": export_filename(exam, "html"),
        "mime": "text/html",
        "label": "⬇ PDF / Print (HTML)",
        "is_pdf": False,
    }
