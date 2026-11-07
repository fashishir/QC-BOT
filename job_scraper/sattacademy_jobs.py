"""SattAcademy job-exam adapter (public page 1 only).

Verified live structure (Sep-Nov 2026):

* Hub          : ``https://sattacademy.com/job-assistant``
* Category     : ``/job-solution/{bangla-slug}``
* Exam listing : ``[data-exam_name]`` cards (duplicated as h4 + button),
                 deduplicated by ``data-subcat_id``.
* MCQ exam     : ``.../all/mcq-questions``

The public exam page exposes 15 question cards. Each leaf card contains
``span.question-span``, four ``label`` options, and a public
``input[name="answer"]`` whose value is 1-4 (0/absent = not published).

Robots (sattacademy.com/robots.txt) disallows ``/*?page=*`` and
``/*&page=*``; this adapter never constructs or follows pagination.
"""

from __future__ import annotations

import re
from urllib.parse import quote, unquote, urljoin

from bs4 import BeautifulSoup

from .logging_setup import get_logger
from .normalize import normalize_ws, parse_date

log = get_logger("sattacademy")

BASE_URL = "https://sattacademy.com"
HUB_URL = f"{BASE_URL}/job-assistant"
CATEGORY_PREFIX = "/job-solution/"

# Category display order follows the hub; these are the two non-job links.
EXCLUDED_CATEGORY_SLUGS = {"mcq", "written"}


def absolute_url(href: str, base: str = BASE_URL) -> str:
    return urljoin(base, href)


def category_slug(url: str) -> str:
    path = unquote(url).split("?")[0].rstrip("/")
    return path.rsplit("/", 1)[-1]


def parse_hub(html: str, page_url: str = HUB_URL) -> list[dict]:
    """Extract the 40 job categories from the hub page."""
    soup = BeautifulSoup(html, "lxml")
    categories: list[dict] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if CATEGORY_PREFIX not in href:
            continue
        full = absolute_url(href, page_url).split("?")[0]
        slug = category_slug(full)
        if not slug or slug in EXCLUDED_CATEGORY_SLUGS or full in seen:
            continue
        seen.add(full)
        name = normalize_ws(a.get_text(" ", strip=True))
        if not name:
            name = slug
        categories.append({
            "slug": slug,
            "name": name,
            "source_url": full,
            "display_order": len(categories) + 1,
        })
    return categories


def parse_category(html: str, page_url: str) -> list[dict]:
    """Parse one category page into unique 2025-2026 exam cards."""
    soup = BeautifulSoup(html, "lxml")
    exams: list[dict] = []
    seen: set[str] = set()
    for card in soup.select("[data-exam_name]"):
        subcat_id = normalize_ws(str(card.get("data-subcat_id") or ""))
        if not subcat_id or subcat_id in seen:
            continue
        exam_url = normalize_ws(str(card.get("data-url") or ""))
        if not exam_url:
            continue
        name = normalize_ws(str(card.get("data-exam_name") or ""))
        if not name:
            continue
        seen.add(subcat_id)
        iso = parse_date(name)
        if iso is None:
            # Some cards embed the date without an ISO suffix; reject only
            # when no 2025/2026 evidence exists at all.
            if not re.search(r"20(?:25|26)", name):
                continue
        year = int(iso[:4]) if iso else int(re.search(r"20(?:25|26)", name).group(0))
        if year not in (2025, 2026):
            continue
        total_raw = normalize_ws(str(card.get("data-total_question") or ""))
        total = int(total_raw) if total_raw.isdigit() else None
        exams.append({
            "subcat_id": subcat_id,
            "exam_name": name,
            "exam_date": iso,
            "year": year,
            "total_questions": total,
            "source_url": absolute_url(exam_url, page_url),
        })
    return exams


def parse_exam_questions(html: str, exam_url: str) -> list[dict]:
    """Parse the 15 public MCQ cards on one exam page (page 1 only)."""
    soup = BeautifulSoup(html, "lxml")
    cards = [
        c for c in soup.select("div.card")
        if c.select_one("span.question-span")
    ]
    # The page nests all questions inside one wrapper card; keep leaf cards.
    leaf_cards = []
    for card in cards:
        nested = [
            child for child in card.select("div.card")
            if child is not card and child.select_one("span.question-span")
        ]
        if not nested:
            leaf_cards.append(card)

    questions: list[dict] = []
    for number, card in enumerate(leaf_cards, start=1):
        stem = card.select_one("span.question-span.white-heading") or card.select_one("span.question-span")
        question_text = normalize_ws(stem.get_text(" ", strip=True)) if stem else ""
        images: list[str] = []
        if stem is not None:
            for img in stem.select("img"):
                src = img.get("src") or img.get("data-src") or ""
                if src:
                    images.append(absolute_url(src, exam_url))
        for img in card.select(".card-header img"):
            src = img.get("src") or ""
            if src:
                full = absolute_url(src, exam_url)
                if full not in images:
                    images.append(full)

        labels = card.select(".reading-mode-data label") or card.select("label")
        options: list[str] = []
        option_review = False
        for label in labels[:4]:
            text = normalize_ws(label.get_text(" ", strip=True))
            if not text:
                for img in label.select("img"):
                    text = normalize_ws(img.get("alt") or "")
                    if text:
                        break
            options.append(text)
        if len(labels) != 4 or len(options) != 4:
            option_review = True

        answer = _extract_answer(card, labels)
        question = {
            "question_no": number,
            "question_text": question_text,
            "options": options,
            "answer_index": answer,
            "answer_source": "sattacademy",
            "answer_confidence": "high",
            "review_status": "needs_review" if (option_review or not question_text) else "auto",
            "images": images,
            "source_url": exam_url,
        }
        questions.append(question)
    return questions


def _extract_answer(card, labels) -> int | None:
    ans_input = card.select_one('input[name="answer"]')
    if ans_input is not None:
        raw = normalize_ws(str(ans_input.get("value") or ""))
        if raw.isdigit():
            value = int(raw)
            if 1 <= value <= 4:
                return value
            return None
    # Fallback: correct option is decorated with a green check icon.
    for index, label in enumerate(labels, start=1):
        block = label.find_parent("div", class_=re.compile(r"col-md-6"))
        scope = block if block is not None else label.parent
        if scope is not None and scope.select_one(".fa-check-circle"):
            return index
    return None


def has_more_pages(html: str) -> bool:
    """True when the page carries ?page= pagination (never followed)."""
    soup = BeautifulSoup(html, "lxml")
    return soup.find("a", href=re.compile(r"[?&]page=\d+")) is not None


def category_url(slug: str) -> str:
    return f"{BASE_URL}{CATEGORY_PREFIX}{quote(slug, safe='')}"


def infer_institution(category_name: str, exam_name: str) -> str | None:
    """Best-effort institution label used only for filtering/display."""
    haystack = f"{category_name} {exam_name}"
    mapping = [
        (("বিসিএস",), "বাংলাদেশ সরকারি কর্ম কমিশন (BPSC)"),
        (("শিক্ষক নিবন্ধন", "প্রভাষক নিবন্ধন", "এনটিআরসিএ"), "বেসরকারি শিক্ষক নিবন্ধন ও প্রত্যয়ন কর্তৃপক্ষ (NTRCA)"),
        (("বাংলাদেশ ব্যাংক",), "বাংলাদেশ ব্যাংক"),
        (("সমন্বিত ব্যাংক",), "সমন্বিত ব্যাংক"),
        (("জুডিসিয়াল", "বিজেএসসি"), "বাংলাদেশ জুডিসিয়াল সার্ভিস কমিশন"),
        (("প্রাথমিক", "উপজেলা / থানা শিক্ষা অফিসার", "এটিইও"), "প্রাথমিক ও গণশিক্ষা মন্ত্রণালয়"),
        (("নার্সিং",), "বাংলাদেশ নার্সিং ও মিডওয়াইফারি কাউন্সিল"),
        (("বিমান",), "বাংলাদেশ বিমান বাহিনী / বিমান বাংলাদেশ এয়ারলাইন্স"),
        (("পোস্টমাস্টার",), "বাংলাদেশ ডাক বিভাগ"),
        (("সিভিল সার্জন",), "স্বাস্থ্য অধিদপ্তর"),
        (("গণপূর্ত", "পল্লী বিদ্যুৎ", "বিআরইবি"), "স্থানীয় সরকার প্রকৌশল অধিদপ্তর / BREB"),
        (("বীমা",), "সাধারণ বীমা কর্পোরেশন"),
        (("কৃষি",), "কৃষি মন্ত্রণালয়"),
        (("শিল্প",), "শিল্প মন্ত্রণালয়"),
        (("শ্রম",), "শ্রম ও কর্মসংস্থান মন্ত্রণালয়"),
        (("ভূমি",), "ভূমি মন্ত্রণালয়"),
        (("স্বরাষ্ট্র", "পুলিশ", "বিজিবি", "র্যাব"), "স্বরাষ্ট্র মন্ত্রণালয়"),
    ]
    for keys, label in mapping:
        if any(key in haystack for key in keys):
            return label
    return category_name or None
