"""Optional OCR for scanned PDFs using Tesseract with Bangla support.

Language packs default to 'ben+eng' (Bangla + English). OCR FAILS SOFT:
if the Tesseract binary or language packs are missing, OCRUnavailable is
raised and the pipeline marks the paper 'ocr_pending' for manual review -
it never crashes a run and never attempts anything hacky.

Requirements (see README):
  * Tesseract binary installed and on PATH (or settings.ocr.tesseract_cmd)
  * Bangla traineddata: 'ben' language pack (e.g. apt install tesseract-ocr-ben)
"""

from __future__ import annotations

import io
from pathlib import Path

from .logging_setup import get_logger

log = get_logger("ocr")


class OCRUnavailable(RuntimeError):
    """OCR cannot run (missing binary / dependency / language pack)."""


def _load_engines():
    try:
        import pytesseract
        import pymupdf
        from PIL import Image
    except ImportError as exc:
        raise OCRUnavailable(f"OCR dependencies missing: {exc}") from exc
    return pytesseract, pymupdf, Image


def tesseract_available(pytesseract) -> bool:
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def ocr_pdf(path: str | Path, languages: str = "ben+eng", max_pages: int = 30,
            tesseract_cmd: str | None = None) -> tuple[str, float | None, int]:
    """OCR a PDF and return (text, mean_confidence, pages_processed).

    Each page is rasterised at 200 DPI and passed to Tesseract with
    image_to_data so per-word confidence values are available.
    """
    pytesseract, pymupdf, image_module = _load_engines()
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    if not tesseract_available(pytesseract):
        raise OCRUnavailable(
            "Tesseract binary not found. Install it (e.g. 'choco install tesseract' / "
            "'apt install tesseract-ocr tesseract-ocr-ben') or set ocr.tesseract_cmd."
        )

    document = pymupdf.open(str(path))
    texts: list[str] = []
    confidences: list[float] = []
    pages_done = 0
    try:
        for page in document:
            if pages_done >= max_pages:
                log.info("OCR page cap (%d) reached for %s", max_pages, Path(path).name)
                break
            pix = page.get_pixmap(dpi=200)
            image = image_module.open(io.BytesIO(pix.tobytes("png")))
            data = pytesseract.image_to_data(
                image, lang=languages, output_type=pytesseract.Output.DICT
            )
            words = [
                str(word) for word, conf in zip(data.get("text", []), data.get("conf", []))
                if str(word).strip()
            ]
            scores = [
                float(conf) for conf in data.get("conf", [])
                if str(conf) not in ("-1", "")
            ]
            texts.append(" ".join(words))
            if scores:
                confidences.append(sum(scores) / len(scores))
            pages_done += 1
    finally:
        document.close()

    text = "\n".join(part for part in texts if part).strip()
    mean_confidence = round(sum(confidences) / len(confidences), 1) if confidences else None
    return text, mean_confidence, pages_done
