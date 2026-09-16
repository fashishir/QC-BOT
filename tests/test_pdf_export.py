"""Tests for server-side PDF export (WeasyPrint) with HTML fallback."""

import json

from ssc_scraper.pdf_export import (
    build_export_payload,
    build_print_html,
    export_filename,
    html_to_pdf,
)


def _exam(**overrides):
    base = {
        "id": 42,
        "exam_name": "SSC Dhaka Physics 2023",
        "board": "dhaka",
        "year": 2023,
        "mcq_url": "https://example.org/q",
    }
    base.update(overrides)
    return base


def _mcq(no=1, text="বাংলা প্রশ্ন", ans="1"):
    return {
        "question_type": "mcq",
        "question_no": no,
        "question_text": text,
        "options_json": json.dumps(
            [{"index": 1, "text": "ক"}, {"index": 2, "text": "খ"}]
        ),
        "correct_answer": ans,
    }


def test_build_print_html_contains_bengali_sections():
    out = build_print_html(_exam(), [_mcq(), {
        "question_type": "written",
        "question_no": 2,
        "question_text": "সৃজনশীল লিখ",
        "options_json": "[]",
    }])
    assert "বহুনির্বাচনি" in out
    assert "সৃজনশীল" in out
    assert "বাংলা" in out
    assert "@page" in out  # print CSS survives into the PDF render


def test_build_print_html_escapes_user_content():
    out = build_print_html(
        _exam(exam_name='<script>alert("x")</script>'),
        [_mcq(text="<b>bold</b>")],
    )
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert "&lt;b&gt;" in out


def test_export_filename_is_filesystem_safe():
    name = export_filename({"board": "dhaka board!", "year": 2023, "id": 7}, "pdf")
    assert name == "dhaka_board__2023_7.pdf"
    assert export_filename({"id": 1}, "html").endswith(".html")


def test_payload_serves_pdf_when_converter_succeeds():
    payload = build_export_payload(
        _exam(), [_mcq()], pdf_converter=lambda _html: b"%PDF-1.4 fake-bytes"
    )
    assert payload["is_pdf"] is True
    assert payload["mime"] == "application/pdf"
    assert payload["file_name"].endswith(".pdf")
    assert payload["data"] == b"%PDF-1.4 fake-bytes"
    assert payload["label"] == "⬇ Download PDF"


def test_payload_falls_back_to_html_when_converter_returns_none():
    payload = build_export_payload(
        _exam(), [_mcq()], pdf_converter=lambda _html: None
    )
    assert payload["is_pdf"] is False
    assert payload["mime"] == "text/html"
    assert payload["file_name"].endswith(".html")
    assert payload["data"].decode("utf-8").startswith("<!DOCTYPE html>")


def test_payload_falls_back_to_html_when_converter_raises():
    def _boom(_html):
        raise OSError("missing pango")

    payload = build_export_payload(_exam(), [_mcq()], pdf_converter=_boom)
    assert payload["is_pdf"] is False
    assert payload["mime"] == "text/html"


def test_html_to_pdf_returns_none_or_pdf_bytes():
    # Must never raise: None (missing system libs, e.g. local Windows
    # without GTK) or real PDF bytes (Streamlit Cloud Debian with
    # packages.txt installed) are both acceptable.
    result = html_to_pdf("<p>hello</p>")
    assert result is None or (
        isinstance(result, bytes) and result.startswith(b"%PDF")
    )
