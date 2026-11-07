"""Text/date normalization helpers shared by parsers, DB, and exports."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date, datetime

BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
OPTION_SYMBOLS = {1: "ক", 2: "খ", 3: "গ", 4: "ঘ"}
OPTION_SYMBOLS_PAREN = {1: "(ক)", 2: "(খ)", 3: "(গ)", 4: "(ঘ)"}

MONTHS_EN = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12, "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

MONTHS_BN = {
    "জানুয়ারি": 1, "ফেব্রুয়ারি": 2, "মার্চ": 3, "এপ্রিল": 4, "মে": 5,
    "জুন": 6, "জুলাই": 7, "আগস্ট": 8, "সেপ্টেম্বর": 9, "অক্টোবর": 10,
    "নভেম্বর": 11, "ডিসেম্বর": 12,
}


def bn_digits_to_ascii(text: str) -> str:
    """Convert Bengali digits to ASCII digits."""
    return (text or "").translate(BN_DIGITS)


def normalize_ws(text: str) -> str:
    """Collapse whitespace and strip zero-width characters."""
    text = unicodedata.normalize("NFC", text or "")
    text = text.replace("\u200b", "").replace("\ufeff", "")
    return re.sub(r"\s+", " ", text).strip()


def parse_date(text: str) -> str | None:
    """Parse a date from common SattAcademy/Live MCQ formats to ISO.

    Supports: ``2025-09-19``, ``১৯ সেপ্টেম্বর, ২০২৫``, ``19 September 2025``,
    ``19-09-2025`` and ``19/09/2025``.
    """
    if not text:
        return None
    raw = normalize_ws(bn_digits_to_ascii(text))

    m = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", raw)
    if m:
        return _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    m = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](20\d{2})\b", raw)
    if m:
        return _safe_date(int(m.group(3)), int(m.group(2)), int(m.group(1)))

    m = re.search(r"\b(\d{1,2})\s+([A-Za-z]+),?\s+(20\d{2})\b", raw)
    if m and m.group(2).lower() in MONTHS_EN:
        return _safe_date(int(m.group(3)), MONTHS_EN[m.group(2).lower()], int(m.group(1)))

    m = re.search(r"\b(\d{1,2})\s+([^\s,]+),?\s+(20\d{2})\b", raw)
    if m and m.group(2) in MONTHS_BN:
        return _safe_date(int(m.group(3)), MONTHS_BN[m.group(2)], int(m.group(1)))

    return None


def _safe_date(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def year_from_date(iso_date: str | None) -> int | None:
    if not iso_date:
        return None
    try:
        return int(iso_date[:4])
    except (TypeError, ValueError):
        return None


def sha256_text(text: str) -> str:
    return hashlib.sha256(normalize_ws(text).encode("utf-8")).hexdigest()


def question_hash(question_text: str, options: list[str]) -> str:
    payload = "|".join([normalize_ws(question_text), *[normalize_ws(o) for o in options]])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def strip_option_label(text: str) -> str:
    """Remove a leading ``ক)`` / ``(A)`` / ``1.`` option label."""
    cleaned = normalize_ws(text)
    cleaned = re.sub(r"^[\(（]?\s*(?:[কখগঘ]|[A-Da-d]|[1-4১-৪])\s*[\)）.।:：-]\s*", "", cleaned)
    return cleaned.strip()


def parse_option_label(text: str) -> int | None:
    """Return 1-4 when *text* starts with a known option marker."""
    cleaned = normalize_ws(text)
    m = re.match(r"^[\(（]?\s*([কখগঘA-Da-d1-4১-৪])\s*[\)）.।:：-]", cleaned)
    if not m:
        return None
    token = m.group(1)
    token = token.translate(BN_DIGITS)
    if token in "ক1১":
        return 1
    if token in "খ2২":
        return 2
    if token in "গ3৩":
        return 3
    if token in "ঘ4৪":
        return 4
    if token.upper() == "A":
        return 1
    if token.upper() == "B":
        return 2
    if token.upper() == "C":
        return 3
    if token.upper() == "D":
        return 4
    return None


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
