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
    "dhaka": ["dhaka", "ঢাকা"],
    "chattogram": ["chattogram", "chittagong", "চট্টগ্রাম"],
    "jessore": ["jessore", "jashore", "যশোর"],
    "dinajpur": ["dinajpur", "দিনাজপুর"],
    "rajshahi": ["rajshahi", "রাজশাহী"],
    "khulna": ["khulna", "খুলনা"],
    "barishal": ["barishal", "barisal", "বরিশাল"],
    "sylhet": ["sylhet", "সিলেট"],
    "rangpur": ["rangpur", "রংপুর"],
    "mymensingh": ["mymensingh", "ময়মনসিংহ", "ময়মনসিংহ"],
    "cumilla": ["cumilla", "comilla", "কুমিল্লা"],
    "madrasah": ["madrasah", "madrasa", "dakhil", "মাদ্রাসা"],
    "technical": ["technical", "vocational", "কারিগরি"],
    "combined": ["combined", "combined board", "all board", "সকল", "সমন্বিত"],
}

# Canonical subject -> aliases (English + Bangla). Longest match wins,
# so 'higher mathematics' is checked before 'mathematics', etc.
SUBJECTS: dict[str, list[str]] = {
    "bangla_1st": ["bangla 1st", "bangla first", "বাংলা ১ম", "বাংলা প্রথম", "bangla sahitya", "বাংলা সাহিত্য"],
    "bangla_2nd": ["bangla 2nd", "bangla second", "বাংলা ২য়", "বাংলা ২য়", "বাংলা দ্বিতীয়", "বাংলা ব্যাকরণ"],
    "bangla": ["bangla", "bengali", "বাংলা"],
    "english_1st": ["english 1st", "english first", "english for today", "ইংরেজি ১ম"],
    "english_2nd": ["english 2nd", "english second", "grammar and composition", "ইংরেজি ২য়", "ইংরেজি ২য়"],
    "english": ["english", "ইংরেজি"],
    "mathematics": ["mathematics", "general math", "গণিত"],
    "higher_mathematics_1st": ["higher math 1st", "higher mathematics 1st", "উচ্চতর গণিত ১ম", "উচ্চতর গণিত প্রথম"],
    "higher_mathematics_2nd": ["higher math 2nd", "higher mathematics 2nd", "উচ্চতর গণিত ২য়", "উচ্চতর গণিত ২য়"],
    "higher_mathematics": ["higher mathematics", "higher math", "উচ্চতর গণিত"],
    "physics_1st": ["physics 1st", "physics first", "পদার্থবিজ্ঞান ১ম", "পদার্থ ১ম"],
    "physics_2nd": ["physics 2nd", "physics second", "পদার্থবিজ্ঞান ২য়", "পদার্থবিজ্ঞান ২য়"],
    "physics": ["physics", "পদার্থবিজ্ঞান", "পদার্থ বিজ্ঞান"],
    "chemistry_1st": ["chemistry 1st", "chemistry first", "রসায়ন ১ম", "রসায়ন প্রথম", "রসায়ন প্রথম"],
    "chemistry_2nd": ["chemistry 2nd", "chemistry second", "রসায়ন ২য়", "রসায়ন দ্বিতীয়", "রসায়ন দ্বিতীয়"],
    "chemistry": ["chemistry", "রসায়ন", "রসায়ন"],
    "biology_1st": ["biology 1st", "জীববিজ্ঞান ১ম", "জীববিজ্ঞান প্রথম"],
    "biology_2nd": ["biology 2nd", "জীববিজ্ঞান ২য়", "জীববিজ্ঞান ২য়", "জীববিজ্ঞান দ্বিতীয়"],
    "biology": ["biology", "জীববিজ্ঞান"],
    "ict": ["ict", "information and communication technology", "আইসিটি", "তথ্য ও যোগাযোগ প্রযুক্তি"],
    "accounting_1st": ["accounting 1st", "হিসাববিজ্ঞান ১ম"],
    "accounting_2nd": ["accounting 2nd", "হিসাববিজ্ঞান ২য়", "হিসাববিজ্ঞান ২য়"],
    "accounting": ["accounting", "হিসাববিজ্ঞান"],
    "finance_1st": ["finance 1st", "ফিন্যান্স ১ম", "ফিনান্স ১ম"],
    "finance_2nd": ["finance 2nd", "ফিন্যান্স ২য়", "ফিন্যান্স ২য়"],
    "finance": ["finance", "banking", "ব্যাংকিং", "ফিন্যান্স", "ফিনান্স", "বিমা"],
    "business_org_1st": ["business organization 1st", "ব্যবসায় সংগঠন ১ম", "ব্যবসায় সংগঠন ১ম"],
    "business_org_2nd": ["business organization 2nd", "ব্যবসায় সংগঠন ২য়", "ব্যবসায় সংগঠন ২য়"],
    "business_studies": [
        "business studies", "business organization", "business entrepreneurship",
        "ব্যবসায় উদ্যোগ", "ব্যবসায় উদ্যোগ", "ব্যবসায় সংগঠন", "ব্যবসায় সংগঠন",
        "production management", "marketing", "উৎপাদন ব্যবস্থাপনা", "বিপণন",
    ],
    "economics_1st": ["economics 1st", "অর্থনীতি ১ম"],
    "economics_2nd": ["economics 2nd", "অর্থনীতি ২য়", "অর্থনীতি ২য়"],
    "economics": ["economics", "অর্থনীতি"],
    "civics_1st": ["civics 1st", "পৌরনীতি ১ম", "সুশাসন ১ম"],
    "civics_2nd": ["civics 2nd", "পৌরনীতি ২য়", "পৌরনীতি ২য়", "সুশাসন ২য়"],
    "civics": ["civics", "পৌরনীতি", "নাগরিকতা", "সুশাসন"],
    "logic_1st": ["logic 1st", "যুক্তিবিদ্যা ১ম"],
    "logic_2nd": ["logic 2nd", "যুক্তিবিদ্যা ২য়", "যুক্তিবিদ্যা ২য়"],
    "logic": ["logic", "যুক্তিবিদ্যা"],
    "sociology_1st": ["sociology 1st", "সমাজবিজ্ঞান ১ম", "সমাজবিজ্ঞান প্রথম"],
    "sociology_2nd": ["sociology 2nd", "সমাজবিজ্ঞান ২য়", "সমাজবিজ্ঞান ২য়"],
    "sociology": ["sociology", "সমাজবিজ্ঞান"],
    "social_work_1st": ["social work 1st", "সমাজকর্ম ১ম", "সমাজকর্ম প্রথম"],
    "social_work_2nd": ["social work 2nd", "সমাজকর্ম ২য়", "সমাজকর্ম ২য়", "সমাজকর্ম দ্বিতীয়"],
    "social_work": ["social work", "সমাজকর্ম"],
    "geography_1st": ["geography 1st", "ভূগোল ১ম"],
    "geography_2nd": ["geography 2nd", "ভূগোল ২য়", "ভূগোল ২য়"],
    "geography": ["geography", "ভূগোল"],
    "history_1st": ["history 1st", "ইতিহাস ১ম"],
    "history_2nd": ["history 2nd", "ইতিহাস ২য়", "ইতিহাস ২য়"],
    "history": ["history", "ইতিহাস"],
    "islamic_studies_1st": ["islamic studies 1st", "islam 1st", "ইসলাম শিক্ষা ১ম", "ইসলাম ১ম"],
    "islamic_studies_2nd": ["islamic studies 2nd", "islam 2nd", "ইসলাম শিক্ষা ২য়", "ইসলাম শিক্ষা ২য়"],
    "islam": ["islam", "ইসলাম"],
    "psychology_1st": ["psychology 1st", "মনোবিজ্ঞান ১ম"],
    "psychology_2nd": ["psychology 2nd", "মনোবিজ্ঞান ২য়", "মনোবিজ্ঞান ২য়"],
    "psychology": ["psychology", "মনোবিজ্ঞান"],
    "statistics_1st": ["statistics 1st", "পরিসংখ্যান ১ম"],
    "statistics_2nd": ["statistics 2nd", "পরিসংখ্যান ২য়", "পরিসংখ্যান ২য়"],
    "statistics": ["statistics", "পরিসংখ্যান"],
    "agriculture_1st": ["agriculture 1st", "agricultural 1st", "কৃষিশিক্ষা ১ম", "কৃষি ১ম"],
    "agriculture_2nd": ["agriculture 2nd", "agricultural 2nd", "কৃষিশিক্ষা ২য়", "কৃষিশিক্ষা ২য়"],
    "agriculture": ["agriculture", "agricultural studies", "কৃষিশিক্ষা", "কৃষি শিক্ষা"],
    "home_science_1st": ["home science 1st", "domestic science 1st", "গার্হস্থ্য ১ম", "গার্হস্থ্যবিজ্ঞান ১ম"],
    "home_science_2nd": ["home science 2nd", "domestic science 2nd", "গার্হস্থ্য ২য়", "গার্হস্থ্য ২য়"],
    "home_science": ["home science", "domestic science", "গার্হস্থ্য", "গৃহব্যবস্থাপনা"],
    "hinduism": ["hinduism", "hindu religion", "হিন্দুধর্ম", "হিন্দু ধর্ম"],
    "buddhism": ["buddhism", "buddhist religion", "বৌদ্ধধর্ম", "বৌদ্ধ ধর্ম"],
    "christianity": ["christianity", "christian religion", "খ্রিষ্টধর্ম", "খ্রিস্টধর্ম"],
    "general_knowledge": [
        "general knowledge", "bangladesh and global studies", "bgs",
        "সাধারণ জ্ঞান", "বাংলাদেশ ও বিশ্বপরিচয়", "বাংলাদেশ ও বিশ্বপরিচয়",
    ],
}

# Canonical paper type -> aliases
PAPER_TYPES: dict[str, list[str]] = {
    "mcq": ["mcq", "multiple choice", "objective", "নৈর্ব্যক্তিক", "বহুনির্বাচনী"],
    "creative": ["creative", "cq", "সৃজনশীল"],
    "written": ["written", "descriptive"],
    "practical": ["practical"],
    "model": ["model", "মডেল"],
    "supplementary": ["supplementary", "compartment", "পরিপূরক"],
    "board_question": ["board question", "question paper", "প্রশ্ন", "বোর্ড"],
}

_YEAR_RE = re.compile(r"\b(20[0-2]\d)\b")
_SET_RE = re.compile(r"\b(?:set|সেট)\s*[:\-#]?\s*([a-d1-4])\b", re.IGNORECASE)
_SHIFT_ALIASES = {
    "morning": ["morning", "সকাল"],
    "day": ["day", "দিন"],
    "evening": ["evening", "afternoon", "বিকাল"],
}
_BANGLA_CHAR_RE = re.compile("[\u0980-\u09ff]")
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
