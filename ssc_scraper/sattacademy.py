"""Satt Academy (sattacademy.com) board-exams source adapter.

URL scheme (verified against the live site, read-only, Sep 2026):
  * Listing : /board-exams/{class-slug}?board={board-slug}&year={year}
  * Exam    : /board-exams/{exam-slug}/mcq  and  /board-exams/{exam-slug}/written

Class slugs (from live dropdown):
  * ssc    -> SSC general
  * dakhil -> SSC madrasah
  * hsc    -> HSC general

Listing cards carry data-id, data-sub_cat, data-year, data-exam_name,
data-total_question and data-mcq-url (+data-written-url).

MCQ pages: each question is a div.card containing
  span.question-span.white-heading (stem, may include <img>),
  .reading-mode-data label (4 options),
  input[name=answer][value=N] (correct option, public),
  [data-id] (remote question id).

Written/CQ pages: each sub-question is an <li> with an
  <a href="/question/..."> anchor. Stimulus rows carry circled numbers,
  sub-questions carry ka/kha/ga/gha markers + marks.

Robots compliance (see sattacademy.com/robots.txt):
  * /board-exams and question pages are allowed.
  * '/*?page=*' and '/*&page=*' are explicitly Disallowed -> this adapter
    NEVER constructs or follows page= links. Listings and exam pages are
    fetched page-1 only; when pagination links are present the record is
    flagged (listing_truncated / questions_truncated) for manual review.
"""

from __future__ import annotations

import re
from urllib.parse import quote, unquote, urljoin

from bs4 import BeautifulSoup

from .logging_setup import get_logger

log = get_logger("sattacademy")

BASE_URL = "https://sattacademy.com"
LISTING_URL_TEMPLATE = BASE_URL + "/board-exams/{class_slug}"

# Class path segment (from the live site dropdowns, verified Sep 2026).
# NOTE: stored as real Bangla text (UTF-8); quote_path() percent-encodes it.
CLASS_SLUGS = {
    "ssc": "নবম-দশম-শ্রেণি-মাধ্যমিক",  # SSC (general)
    "dakhil": "নবম-দশম-শ্রেণি-দাখিল",  # SSC (madrasah)
    "hsc": "একাদশ-দ্বাদশ-শ্রেণি",  # HSC (general, verified live Sep 2026)
}

# Board dropdown value -> canonical board name
BOARD_SLUGS = {
    "ঢাকা-বোর্ড": "dhaka",
    "রাজশাহী-বোর্ড": "rajshahi",
    "চট্টগ্রাম-বোর্ড": "chattogram",
    "সিলেট-বোর্ড": "sylhet",
    "যশোর-বোর্ড": "jessore",
    "কুমিল্লা-বোর্ড": "cumilla",
    "দিনাজপুর-বোর্ড": "dinajpur",
    "বরিশাল-বোর্ড": "barishal",
    "সকল-বোর্ড": "combined",
    "ময়মনসিংহ-বোর্ড": "mymensingh",
    "মাদ্রাসা-শিক্ষা-বোর্ড": "madrasah",
    "কারিগরি-শিক্ষা-বোর্ড": "technical",
    "সমন্বিত-বোর্ড": "combined",
}


def quote_path(text: str) -> str:
    """Percent-encode a Bangla URL path segment."""
    return quote(text, safe="")


def listing_url(class_key: str, board_slug: str, year: int) -> str:
    """Build the board+year listing URL for one class. No page=, ever."""
    return (
        LISTING_URL_TEMPLATE.format(class_slug=quote_path(CLASS_SLUGS[class_key]))
        + f"?board={quote_path(board_slug)}&year={int(year)}"
    )


def parse_listing(html: str, page_url: str) -> list[dict]:
    """Parse one listing page into exam dicts (board/year come from URL)."""
    soup = BeautifulSoup(html, "lxml")
    exams: list[dict] = []
    for card in soup.select("div.loginAlertModal"):
        mcq_url = (card.get("data-mcq-url") or "").strip()
        if not mcq_url:
            continue
        written_url = (card.get("data-written-url") or "").strip()
        parent = card.find_parent()
        if not written_url:
            # Fallback: sibling anchors carry the mcq/written pair.
            if parent is not None:
                own = parent.find_all("a", href=True)
                hrefs = [urljoin(page_url, a["href"]) for a in own]
                mcq_candidates = [h for h in hrefs if h.rstrip("/").endswith("/mcq")]
                written_candidates = [h for h in hrefs if h.rstrip("/").endswith("/written")]
                if mcq_candidates:
                    mcq_url = mcq_candidates[0]
                if written_candidates:
                    written_url = written_candidates[0]
        written_url = written_url or None
        mcq_count = cq_count = None
        count_scope = parent if parent is not None else card
        badge_text = count_scope.get_text(separator=' ', strip=True)
        mcq_match = re.search(r'MCQ\s+(\d{1,3})(?!\d)', badge_text)
        cq_match = re.search(r'(?<![A-Z])CQ\s+(\d{1,3})(?!\d)', badge_text)
        if mcq_match:
            mcq_count = int(mcq_match.group(1))
        if cq_match:
            cq_count = int(cq_match.group(1))
        title_anchor = card.find("a", class_="text-hover-primary")
        title = title_anchor.get_text(strip=True) if title_anchor else unquote(mcq_url)
        try:
            year = int(card.get("data-year") or 0) or None
        except (TypeError, ValueError):
            year = None
        try:
            total = int(card.get("data-total_question") or 0) or None
        except (TypeError, ValueError):
            total = None
        exams.append({
            "remote_id": card.get("data-id"),
            "exam_name": (card.get("data-exam_name") or title).strip(),
            "title": title,
            "sub_cat": (card.get("data-sub_cat") or "").strip(),
            "year": year,
            "total_questions": total,
            "mcq_count": mcq_count,
            "cq_count": cq_count,
            "mcq_url": mcq_url,
            "written_url": written_url,
        })
    return exams


def listing_is_truncated(html: str) -> bool:
    """True when the listing spans more pages (page 2 link present).

    The bot must not follow these (robots Disallow) - callers log and flag.
    """
    soup = BeautifulSoup(html, "lxml")
    return soup.find("a", href=re.compile(r"[?&]page=\d+")) is not None


def exam_has_more_pages(html: str) -> bool:
    """True when an exam page has ?page=N pagination (robots-disallowed).

    Both MCQ (30 Qs over 3 pages) and written (55 CQs over 2 pages) paginate.
    We collect page-1 only and flag the exam as questions_truncated.
    """
    soup = BeautifulSoup(html, "lxml")
    return soup.find("a", href=re.compile(r"[?&]page=\d+")) is not None


def _absolute_src(src: str, page_url: str) -> str:
    if not src:
        return src
    return urljoin(page_url, src)


def _parse_mcq_card(card, number: int, exam_url: str, question_type: str) -> dict:
    """Parse one new-style MCQ card (div.card with reading-mode-data)."""
    stem = card.select_one("span.question-span.white-heading")
    if stem is None:
        stem = card.select_one("span.question-span")
    stem_text = stem.get_text(separator=" ", strip=True) if stem else ""
    stem_images = []
    if stem is not None:
        for img in stem.select("img"):
            src = img.get("src") or img.get("data-src") or ""
            if src:
                stem_images.append(_absolute_src(src, exam_url))
    # Also check card-header figure images that belong to the stem
    if card is not None:
        for img in card.select(".card-header img"):
            src = img.get("src") or ""
            if src:
                abs_src = _absolute_src(src, exam_url)
                if abs_src not in stem_images:
                    stem_images.append(abs_src)

    options: list[dict] = []
    # Preferred: reading-mode labels (public, stable)
    labels = card.select(".reading-mode-data label")
    if not labels:
        labels = card.select("label")
    for index, label in enumerate(labels, start=1):
        opt_images = []
        for img in label.select("img"):
            src = img.get("src") or ""
            if src:
                opt_images.append(_absolute_src(src, exam_url))
        options.append({
            "index": index,
            "text": label.get_text(separator=" ", strip=True),
            "images": opt_images,
        })

    # Correct answer: public hidden input + green check icon fallback
    answer = None
    ans_input = card.select_one('input[name="answer"]')
    if ans_input is not None and (ans_input.get("value") or "").strip().isdigit():
        try:
            answer = str(int(ans_input.get("value")))
        except (TypeError, ValueError):
            answer = None
    if answer is None:
        # Fallback: the correct option carries fa-check-circle
        for idx, label in enumerate(labels, start=1):
            opt_block = label.find_parent("div", class_=re.compile(r"col-md-6"))
            scope = opt_block if opt_block is not None else label.parent
            if scope is not None and scope.select_one(".fa-check-circle"):
                answer = str(idx)
                break

    # Remote question id: data-id on click-option, or label for="kkradio_optionX_ID"
    ques_id = None
    click = card.select_one("[data-id]")
    if click is not None and str(click.get("data-id") or "").strip().isdigit():
        ques_id = str(click.get("data-id")).strip()
    if ques_id is None:
        for label in labels:
            m = re.search(r"kkradio_option\d+_(\d+)", label.get("for") or "")
            if m:
                ques_id = m.group(1)
                break
    if ques_id is None:
        # Legacy fixture: input.choosen-option
        checkbox = card.select_one("input.choosen-option")
        if checkbox is not None:
            ques_id = (
                checkbox.get("data-ques_id")
                or (checkbox.get("name") or "").replace("option_", "")
                or None
            )

    # Legacy community votes (kept for backwards compat; often absent now)
    votes: dict[str, int] = {}
    for vote in card.select("[class*=vote_option_]"):
        classes = " ".join(vote.get("class", []))
        match = re.search(r"vote_option_(\d+)", classes)
        if match:
            try:
                votes[f"option_{match.group(1)}"] = int(vote.get_text(strip=True))
            except (TypeError, ValueError):
                pass

    # Canonical per-question URL (anchor to /mcq/... or /all-mcq/...)
    source_url = exam_url
    anchor = card.select_one('a[href*="/mcq/"]')
    if anchor is not None and anchor.get("href"):
        source_url = urljoin(exam_url, anchor.get("href"))

    return {
        "remote_ques_id": ques_id,
        "question_no": number,
        "question_type": question_type,
        "question_text": stem_text,
        "options_json": {
            "options": options,
            "images": stem_images,
            "community_votes": votes,
        },
        "answer": answer,
        "source_url": source_url,
    }


def _parse_written_li(li, number: int, exam_url: str) -> dict | None:
    """Parse one written <li> (stimulus or ka/kha/ga/gha sub-question)."""
    anchor = li.select_one('a[href*="/question/"]')
    if anchor is None:
        return None
    text = anchor.get_text(separator=" ", strip=True)
    if not text:
        return None
    href = urljoin(exam_url, anchor.get("href"))
    # remote id = trailing numeric suffix of /question/ slug when present
    ques_id = None
    m = re.search(r"-(\d+)(?:/?)$", anchor.get("href") or "")
    if m:
        ques_id = m.group(1)
    # Full li text carries marker + marks, e.g. "(ক) | খাদ্য কী? | ১ | Ans"
    li_text = li.get_text(separator=" ", strip=True)
    marker = None
    m_marker = re.match(r"\s*[\(（]\s*([^\)）]+?)\s*[\)）]", li_text)
    if m_marker:
        marker = m_marker.group(1).strip()
    # images inside the anchor/li
    images = []
    for img in li.select("img"):
        src = img.get("src") or ""
        if src:
            images.append(_absolute_src(src, exam_url))
    return {
        "remote_ques_id": ques_id,
        "question_no": number,
        "question_type": "written",
        "question_text": text,
        "options_json": {
            "options": [],
            "images": images,
            "marker": marker,
            "li_text": li_text[:500],
            "question_href": href,
        },
        "answer": None,  # CQ answers are login-gated
        "source_url": href,
    }


def parse_exam_questions(html: str, exam_url: str, question_type: str) -> list[dict]:
    """Parse one /mcq or /written exam page (page-1 only) into question dicts.

    MCQ: new card layout (answer + images extracted) with legacy fallback.
    Written/CQ: each <li> with /question/ anchor becomes one record.
    """
    soup = BeautifulSoup(html, "lxml")
    questions: list[dict] = []

    if question_type == "written":
        lis = soup.find_all("li")
        number = 0
        for li in lis:
            if not li.find("a", href=lambda h: h and "/question/" in h):
                continue
            rec = _parse_written_li(li, number + 1, exam_url)
            if rec is None:
                continue
            number += 1
            rec["question_no"] = number
            questions.append(rec)
        if questions:
            return questions
        # Fallback: if no li-based questions, try MCQ-style stems (some
        # written pages reuse the card layout)
        question_type = "written"  # keep type, fall through to card parser

    # --- MCQ / card parser ---
    # New layout: div.card containing span.question-span
    cards = [
        c for c in soup.select("div.card")
        if c.select_one("span.question-span")
    ]
    if cards:
        for number, card in enumerate(cards, start=1):
            questions.append(_parse_mcq_card(card, number, exam_url, question_type))
        return questions

    # Legacy layout (offline fixtures): bare stems + toolbar-div scope
    stems = soup.select("span.question-span.white-heading")
    for number, stem in enumerate(stems, start=1):
        stem_text = stem.get_text(separator=" ", strip=True)
        container = stem.find_parent("div", class_="toolbar-div")
        scope = container.parent if container is not None else stem.parent
        options: list[dict] = []
        if scope is not None:
            labels = scope.select("label")
            for index, label in enumerate(labels, start=1):
                options.append({
                    "index": index,
                    "text": label.get_text(separator=" ", strip=True),
                })
            ques_id = None
            checkbox = scope.select_one("input.choosen-option")
            if checkbox is not None:
                ques_id = (
                    checkbox.get("data-ques_id")
                    or (checkbox.get("name") or "").replace("option_", "")
                    or None
                )
        else:
            ques_id = None
        votes: dict[str, int] = {}
        if scope is not None:
            for vote in scope.select("[class*=vote_option_]"):
                classes = " ".join(vote.get("class", []))
                match = re.search(r"vote_option_(\d+)", classes)
                if match:
                    try:
                        votes[f"option_{match.group(1)}"] = int(vote.get_text(strip=True))
                    except (TypeError, ValueError):
                        pass
        questions.append({
            "remote_ques_id": ques_id,
            "question_no": number,
            "question_type": question_type,
            "question_text": stem_text,
            "options_json": {"options": options, "community_votes": votes},
            "answer": None,
            "source_url": exam_url,
        })
    return questions
