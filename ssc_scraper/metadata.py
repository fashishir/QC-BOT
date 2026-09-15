"""Metadata extraction and normalization.

Extracts structured facets (board, year, subject, paper_type, set_code,
shift, language, ...) from file names, page context text and PDF text.
Supports both English and Bangla naming conventions; Bangla numerals are
converted before year detection.

All lists below are declarative dictionaries so they are trivial to extend.
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

from .logging_setup import get_logger
from .utils import convert_bangla_digits, normalized_text

log = get_logger("metadata")

YEAR_MIN = 2005
YEAR_MAX = 2026

# Canonical board name -> aliases (English spellings + Bangla words)
BOARDS: dict[str, list[str]] = {
    "dhaka": ["dhaka"],
    "chattogram": ["chattogram", "chittagong"],
    "rajshahi": ["rajshahi"],
    "khulna": ["khulna"],
    "barishal": ["barishal", "barisal"],
    "sylhet": ["sylhet"],
    "rangpur": ["rangpur"],
    "mymensingh": ["mymensingh"],
    "cumilla": ["cumilla", "comilla"],
    "madrasah": ["madrasah", "madrasa", "dakhil"],
    "technical": ["technical", "vocational"],
}

# Canonical subject -> aliases (English + Bangla). Kept conservative:
# aliases are matched with word boundaries to avoid false positives.
SUBJECTS: dict[str, list[str]] = {
    "bangla": ["bangla", "bengali", "\u09ac\u09be\u0982\u09b2\u09be"],
    "english": ["english", "\u0987\u0982\u09b0\u09c7\u099c\u09bf"],
    "mathematics": ["mathematics", "math", "general math", "\u0997\u09a3\u09bf\u09a4"],
    "higher_mathematics": [
        "higher mathematics", "higher math", "\u0989\u099a\u09cd\u099a\u09a4\u09b0 \u0997\u09a3\u09bf\u09a4",
    ],
    "physics": ["physics", "\u09aa\u09a6\u09be\u09b0\u09cd\u09a5\u09ac\u09bf\u099c\u09cd\u099e\u09be\u09a8"],
    "chemistry": ["chemistry", "\u09b0\u09b8\u09be\u09af\u09bc\u09a8"],
    "biology": ["biology", "\u099c\u09c0\u09ac\u09ac\u09bf\u099c\u09cd\u099e\u09be\u09a8"],
    "ict": ["ict", "information and communication technology", "\u0986\u0987\u09b8\u09bf\u099f\u09bf"],
    "accounting": ["accounting", "\u09b9\u09bf\u09b8\u09be\u09ac\u09ac\u09bf\u099c\u09cd\u099e\u09be\u09a8"],
    "business_studies": [
        "business studies", "business organization", "business entrepreneurship",
        "\u09ac\u09cd\u09af\u09ac\u09b8\u09be\u09af\u09bc \u0989\u09a6\u09cd\u09af\u09cb\u0997",
        "\u09ac\u09cd\u09af\u09ac\u09b8\u09be\u09af\u09bc \u09b8\u0982\u0997\u09a0\u09a8",
    ],
    "economics": ["economics", "\u0985\u09b0\u09cd\u09a5\u09a8\u09c0\u09a4\u09bf"],
    "agriculture": ["agriculture", "agricultural studies", "\u0995\u09c3\u09b7\u09bf\u09b6\u09bf\u0995\u09cd\u09b7\u09be"],
    "social_work": ["social work", "\u09b8\u09ae\u09be\u099c\u0995\u09b0\u09cd\u09ae"],
    "islam": ["islam", "\u0987\u09b8\u09b2\u09be\u09ae"],
    "hinduism": ["hinduism", "hindu religion", "\u09b9\u09bf\u09a8\u09cd\u09a6\u09c1\u09a7\u09b0\u09cd\u09ae"],
    "buddhism": ["buddhism", "buddhist religion", "\u09ac\u09cc\u09a6\u09cd\u09a7\u09a7\u09b0\u09cd\u09ae"],
    "christianity": ["christianity", "christian religion", "\u0996\u09cd\u09b0\u09bf\u09b7\u09cd\u099f\u09a7\u09b0\u09cd\u09ae"],
    "general_knowledge": [
        "general knowledge", "bangladesh and global studies", "bgs",
        "\u09b8\u09be\u09a7\u09be\u09b0\u09a3 \u099c\u09cd\u099e\u09be\u09a8",
        "\u09ac\u09be\u0982\u09b2\u09be\u09a6\u09c7\u09b6 \u0993 \u09ac\u09bf\u09b6\u09cd\u09ac\u09aa\u09b0\u09bf\u099a\u09af\u09bc",
    ],
}

# Canonical paper type -> aliases
PAPER_TYPES: dict[str, list[str]] = {
    "mcq": ["mcq", "multiple choice", "objective", "\u09a8\u09c8\u09b0\u09cd\u09ac\u09cd\u09af\u0995\u09cd\u09a4\u09bf\u0995"],
    "creative": ["creative", "cq", "\u09b8\u09c3\u099c\u09a8\u09b6\u09c0\u09b2"],
    "written": ["written", "descriptive"],
    "practical": ["practical"],
    "model": ["model", "\u09ae\u09a1\u09c7\u09b2"],
    "supplementary": ["supplementary", "compartment", "\u09aa\u09b0\u09bf\u09aa\u09c2\u09b0\u0995"],
    "board_question": ["board question", "question paper", "\u09aa\u09cd\u09b0\u09b6\u09cd\u09a8", "\u09ac\u09cb\u09b0\u09cd\u09a1"],
}

_YEAR_RE = re.compile(r"\b(20[0-2]\d)\b")
_SET_RE = re.compile(r"\b(?:set|\u09b8\u09c7\u099f)\s*[:\-#]?\s*([a-d1-4])\b", re.IGNORECASE)
_SHIFT_ALIASES = {
    "morning": ["morning", "\u09b8\u0995\u09be\u09b2"],
    "day": ["day", "\u09a6\u09bf\u09a8"],
    "evening": ["evening", "afternoon", "\u09ac\u09bf\u0995\u09be\u09b2"],
}
_BANGLA_CHAR_RE = re.compile(r"[\u0980-\u09ff]")
_ASCII_LETTER_RE = re.compile(r"[a-zA-Z]")


def _contains_word(text: str, word: str) -> bool:
    """Word-boundary aware containment (safe for Bangla script too)."""
    if not text or not word:
        return False
    pattern = r"(?<![\w])" + re.escape(word) + r"(?![\w])"
    return re.search(pattern, text) is not None


def extract_year(text: str) -> int | None:
    text = convert_bangla_digits(text)
    for match in _YEAR_RE.finditer(text):
        year = int(match.group(1))
        if YEAR_MIN <= year <= YEAR_MAX:
            return year
    return None


def detect_language(text: str) -> str | None:
    """Rough script-based language detection: bangla | english | mixed."""
    if not text:
        return None
    bangla = len(_BANGLA_CHAR_RE.findall(text))
    ascii_letters = len(_ASCII_LETTER_RE.findall(text))
    if bangla == 0 and ascii_letters == 0:
        return None
    if bangla > 0 and ascii_letters > 0:
        return "mixed"
    return "bangla" if bangla > 0 else "english"


class MetadataExtractor:
    """Extracts normalized metadata facets from text derived from files/pages."""

    def extract(self, text: str) -> dict:
        """Extract all recognized facets from *text* into a partial record dict."""
        if not text:
            return {}
        normalized = normalized_text(convert_bangla_digits(text))
        result: dict = {}

        year = extract_year(normalized)
        if year:
            result["year"] = year

        for board, aliases in BOARDS.items():
            if any(_contains_word(normalized, normalized_text(a)) for a in aliases):
                result["board"] = board
                break

        # Longest aliases first so 'higher mathematics' beats 'mathematics'.
        subject_pairs = [
            (alias, subject) for subject, aliases in SUBJECTS.items() for alias in aliases
        ]
        subject_pairs.sort(key=lambda pair: len(pair[0]), reverse=True)
        for alias, subject in subject_pairs:
            if _contains_word(normalized, normalized_text(alias)):
                result["subject"] = subject
                break

        paper_type_pairs = [
            (alias, paper_type) for paper_type, aliases in PAPER_TYPES.items() for alias in aliases
        ]
        paper_type_pairs.sort(key=lambda pair: len(pair[0]), reverse=True)
        for alias, paper_type in paper_type_pairs:
            if _contains_word(normalized, normalized_text(alias)):
                result["paper_type"] = paper_type
                break

        set_match = _SET_RE.search(convert_bangla_digits(text))
        if set_match:
            result["set_code"] = set_match.group(1).upper()

        for shift, aliases in _SHIFT_ALIASES.items():
            if any(_contains_word(normalized, a) for a in aliases):
                result["shift"] = shift
                break

        exam_code_match = re.search(
            r"\b(?:exam\s*code|examcode)\s*[:\-]?\s*([a-z0-9\-]{3,15})\b",
            normalized,
        )
        if exam_code_match:
            result["exam_code"] = exam_code_match.group(1).upper()

        language = detect_language(text)
        if language:
            result["language"] = language

        return result

    # ------------------------------------------------------------ convenience
    def from_filename(self, file_name: str) -> dict:
        """Extract metadata from a file name (hyphens/underscores become spaces)."""
        spaced = re.sub(r"[-_]+", " ", str(file_name or ""))
        return self.extract(spaced)

    def from_url_and_context(self, url: str, context: str = "") -> dict:
        """Extract metadata from a URL path and the page context of the link."""
        path = unquote(urlparse(url).path)
        url_text = path.replace("/", " ")
        return self.extract(f"{url_text} {context or ''}")

    def from_pdf_text(self, text: str) -> dict:
        """Extract metadata from PDF text (first page usually identifies the paper)."""
        if not text:
            return {}
        return self.extract(text[:5000])
