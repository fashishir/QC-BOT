"""Text extraction from PDFs (pdfplumber primary, PyMuPDF fallback).

For scanned/image-only PDFs the result is empty text - the OCR module
handles those optionally. Page count is returned even when no text is
found so the pipeline knows how many pages were processed.
"""

from __future__ import annotations

from pathlib import Path

from .logging_setup import get_logger

log = get_logger("text")

# Do not store arbitrarily large texts in the database
MAX_TEXT_CHARS = 2_000_000


def extract_pdf_text(path: str | Path) -> tuple[str, int, str]:
    """Extract text from a PDF.

    Returns (text, page_count, method) where method is one of
    'pdfplumber', 'pymupdf', 'none' (no text layer) or 'missing' (file gone).
    """
    pdf_path = Path(path)
    if not pdf_path.exists():
        log.warning("PDF not found on disk: %s", pdf_path)
        return "", 0, "missing"

    pages = 0

    # ---- pdfplumber (best layout fidelity) ----
    try:
        import pdfplumber

        with pdfplumber.open(str(pdf_path)) as pdf:
            pages = len(pdf.pages)
            text = "\n".join((page.extract_text() or "") for page in pdf.pages)
        text = text.strip()
        if text:
            return text[:MAX_TEXT_CHARS], pages, "pdfplumber"
        log.debug("pdfplumber found no text layer in %s (likely scanned)", pdf_path.name)
    except ImportError:
        log.debug("pdfplumber is not installed")
    except Exception as exc:
        log.warning("pdfplumber failed on %s: %s", pdf_path.name, exc)

    # ---- PyMuPDF fallback (fast, robust) ----
    try:
        import pymupdf

        document = pymupdf.open(str(pdf_path))
        try:
            pages = document.page_count
            text = "\n".join(page.get_text() for page in document)
        finally:
            document.close()
        text = text.strip()
        if text:
            return text[:MAX_TEXT_CHARS], pages, "pymupdf"
    except ImportError:
        log.debug("PyMuPDF is not installed")
    except Exception as exc:
        log.warning("PyMuPDF failed on %s: %s", pdf_path.name, exc)

    return "", pages, "none"


def extract_doc_text(path: str | Path) -> tuple[str, int, str]:
    """Best-effort text extraction for DOC/DOCX (no dependency guaranteed).

    DOCX files are ZIP archives; the main document XML is read directly to
    avoid adding python-docx as a hard dependency. Legacy .doc returns empty.
    """
    doc_path = Path(path)
    if not doc_path.exists():
        return "", 0, "missing"
    if doc_path.suffix.lower() == ".docx":
        try:
            import re
            import zipfile

            with zipfile.ZipFile(doc_path) as archive:
                xml = archive.read("word/document.xml").decode("utf-8", errors="ignore")
            text = re.sub(r"<[^>]+>", " ", xml)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:MAX_TEXT_CHARS], 0, "docx-zip"
        except Exception as exc:
            log.warning("DOCX extraction failed on %s: %s", doc_path.name, exc)
    return "", 0, "none"
