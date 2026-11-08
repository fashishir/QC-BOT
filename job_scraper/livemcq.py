"""Live MCQ public solution-page parser.

Approved source: ``web.livemcq.com`` blog solution pages that embed the full
question set as ``div.qc`` blocks. Each block exposes the question number,
stem, four options, and marks the correct option with
``.qc__opt--correct`` (plus occasional ``.qc__answer-note`` text).

Only questions/options/answers are extracted. Explanations, which Live MCQ
publishes for some questions, are deliberately discarded.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .logging_setup import get_logger
from .normalize import bn_digits_to_ascii, normalize_ws, parse_date, parse_option_label

log = get_logger("livemcq")

BASE_URL = "https://web.livemcq.com"


def parse_solution_page(html: str, page_url: str) -> dict:
    """Parse a Live MCQ solution page into an exam metadata + question dict.

    Returns ``{"title", "dates", "questions"}``. Questions are clean enough
    for publication; malformed blocks are marked ``needs_review``.
    """
    soup = BeautifulSoup(html, "lxml")
    h1 = soup.find("h1")
    title = normalize_ws(h1.get_text(" ", strip=True)) if h1 else ""
    dates = sorted(set(_find_dates(soup)))

    questions: list[dict] = []
    seen_numbers: set[int] = set()
    for sequence, block in enumerate(soup.select("div.qc"), start=1):
        parsed = _parse_block(block, sequence, page_url)
        if parsed is None:
            continue
        if parsed["question_no"] in seen_numbers:
            parsed["review_status"] = "needs_review"
        seen_numbers.add(parsed["question_no"])
        questions.append(parsed)

    return {"title": title, "dates": dates, "questions": questions}


def parse_solution_sections(html: str, page_url: str) -> list[dict]:
    """Split a multi-exam solution page into date-labelled sections.

    Some Live MCQ pages stack several exam solutions on one URL. Each
    ``div.qc`` block belongs to the most recent ``... প্রশ্ন সমাধান <year>``
    heading and may carry a ``পরীক্ষার তারিখ`` heading with the actual exam
    date. The caller can then import exactly one eligible section instead of
    every question on the page.
    """
    soup = BeautifulSoup(html, "lxml")
    sections: list[dict] = []
    current: dict = {"heading": "", "date": None, "questions": []}
    sequence = 0

    for node in soup.select("h2, h3, h4, div.qc"):
        if node.name == "div":
            sequence += 1
            parsed = _parse_block(node, sequence, page_url)
            if parsed is not None:
                current["questions"].append(parsed)
            continue

        text = normalize_ws(node.get_text(" ", strip=True))
        if node.name == "h2" and re.search(r"প্রশ্ন\s*সমাধান\s*[০-৯]{4}", text):
            if current["heading"] or current["questions"]:
                sections.append(current)
            current = {"heading": text, "date": None, "questions": []}
        elif "পরীক্ষার তারিখ" in text:
            current["date"] = parse_date(text)

    if current["heading"] or current["questions"]:
        sections.append(current)
    return sections


def _find_dates(soup: BeautifulSoup) -> list[str]:
    text = soup.get_text(" ", strip=True)
    found: list[str] = []
    for pattern in (
        r"\b20\d{2}-\d{1,2}-\d{1,2}\b",
        r"\b\d{1,2}\s+(?:জানুয়ারি|ফেব্রুয়ারি|মার্চ|এপ্রিল|মে|জুন|জুলাই|আগস্ট|সেপ্টেম্বর|অক্টোবর|নভেম্বর|ডিসেম্বর),?\s+২০\d{2}\b",
        r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December),?\s+20\d{2}\b",
    ):
        for match in re.findall(pattern, text):
            iso = parse_date(match)
            if iso:
                found.append(iso)
    return found


def _question_number(block) -> int | None:
    node = block.select_one(".qc__num")
    raw = bn_digits_to_ascii(normalize_ws(node.get_text(" ", strip=True) if node else ""))
    match = re.search(r"\d+", raw)
    return int(match.group(0)) if match else None


def _parse_block(block, sequence: int, page_url: str) -> dict | None:
    q_node = block.select_one(".qc__q")
    question_text = normalize_ws(q_node.get_text(" ", strip=True)) if q_node else ""
    if not question_text:
        return None

    number = _question_number(block) or sequence
    raw_options = block.select(".qc__opt")
    options: list[str] = []
    correct_positions: list[int] = []
    for position, opt in enumerate(raw_options, start=1):
        label_node = opt.select_one(".qc__opt-label")
        text_node = opt.select_one(".qc__opt-text")
        label = normalize_ws(label_node.get_text(" ", strip=True)) if label_node else ""
        text = normalize_ws(text_node.get_text(" ", strip=True)) if text_node else ""
        if not text:
            text = normalize_ws(opt.get_text(" ", strip=True))
            # Drop a duplicated leading option marker from the full text.
            if label and text.startswith(label):
                text = normalize_ws(text[len(label):])
        image_urls = []
        for img in opt.select("img"):
            src = img.get("src") or img.get("data-src") or ""
            if src:
                image_urls.append(urljoin(page_url, src))
        options.append(text or (image_urls[0] if image_urls else ""))
        if "qc__opt--correct" in (opt.get("class") or []):
            correct_positions.append(position)

    answer: int | None = None
    review = "auto"
    confidence = "high"

    if len(correct_positions) == 1 and 1 <= correct_positions[0] <= 4:
        answer = correct_positions[0]
    elif len(correct_positions) == 1 and correct_positions[0] > 4:
        review = "needs_review"
        confidence = "low"
    else:
        answer = _answer_from_note(block, options)
        if answer is None and len(correct_positions) > 1:
            review = "needs_review"
            confidence = "low"

    if len(options) < 4:
        review = "needs_review"
        confidence = "low" if review == "needs_review" else confidence
    elif len(options) > 4:
        # Trim answer-note artefacts and trailing duplicate lines only when
        # the first four positions still carry the real options.
        cleaned = _trim_extra_options(options)
        if cleaned is not None:
            options = cleaned
        else:
            review = "needs_review"
            confidence = "low"

    if review == "auto" and answer is not None and answer > len(options):
        answer = None
        review = "needs_review"
        confidence = "low"

    # If the note explicitly says the question was cancelled / has no answer.
    note = normalize_ws(
        (block.select_one(".qc__answer-note").get_text(" ", strip=True)
         if block.select_one(".qc__answer-note") else "")
    )
    if answer is None and any(marker in note for marker in ("বাতিল", "নেই", "প্রযোজ্য নয়")):
        review = "auto"
        confidence = "high"

    explanation = _extract_explanation(block)

    return {
        "question_no": number,
        "question_text": question_text,
        "options": options[:4],
        "answer_index": answer if answer in (1, 2, 3, 4) else None,
        "answer_source": "livemcq",
        "answer_confidence": confidence,
        "review_status": review,
        "explanation": explanation,
        "images": [],
        "source_url": page_url,
    }


def _extract_explanation(block) -> str | None:
    expl_node = block.select_one(".qc__expl-body")
    if not expl_node:
        expl_node = block.select_one("details.qc__expl, .qc__expl, .qc__explanation")
    if not expl_node:
        return None

    # Strip out toggle/summary headers
    lines: list[str] = []
    for elem in expl_node.children:
        if getattr(elem, "name", None) == "summary":
            continue
        txt = elem.get_text("\n") if hasattr(elem, "get_text") else str(elem)
        for line in txt.split("\n"):
            normalized = normalize_ws(line)
            if normalized and normalized != "ব্যাখ্যা দেখুন":
                lines.append(normalized)

    if not lines:
        # Fallback to direct text if no children iteration gave text
        for line in expl_node.get_text("\n").split("\n"):
            normalized = normalize_ws(line)
            if normalized and normalized != "ব্যাখ্যা দেখুন":
                lines.append(normalized)

    if not lines:
        return None

    cleaned = "\n".join(lines)
    cleaned = re.sub(r"^ব্যাখ্যা\s*[:ঃ\-–—]\s*", "", cleaned, flags=re.IGNORECASE).strip()
    if any(marker in cleaned for marker in ("Live MCQ অ্যাপ", "অ্যাপ ইনস্টল করুন", "অ্যাপ ইন্সটল করুন", "অথেনটিক ব্যাখ্যা দেখতে")):
        return None
    return cleaned or None


def _trim_extra_options(options: list[str]) -> list[str] | None:
    """Return four options when extras are obvious answer-note/duplicate lines."""
    cleaned = [
        opt for opt in options
        if opt and not re.match(r"^সঠিক\s*উত্তর", opt)
    ]
    # De-duplicate exact consecutive duplicates introduced by markup glitches.
    deduped: list[str] = []
    for opt in cleaned:
        if not deduped or normalize_ws(deduped[-1]) != normalize_ws(opt):
            deduped.append(opt)
    return deduped[:4] if len(deduped) >= 4 else None


def _answer_from_note(block, options: list[str]) -> int | None:
    note_node = block.select_one(".qc__answer-note")
    if note_node is None:
        return None
    note = normalize_ws(note_node.get_text(" ", strip=True))
    match = re.search(r"সঠিক\s*উত্তর\s*[:\-]\s*(.+)", note)
    if not match:
        return None
    body = normalize_ws(match.group(1))
    if any(marker in body.split("।")[0] for marker in ("বাতিল", "নেই", "প্রযোজ্য নয়")):
        return None

    index = parse_option_label(body)
    if index and index <= len(options):
        return index
    # "৩ নং" / "3" style.
    m = re.match(r"^[\(（]?\s*([1-4১-৪])\s*(?:নং|\)|）|$)", bn_digits_to_ascii(body))
    if m:
        return int(m.group(1))
    # Match the note text against an option's text.
    plain = re.sub(r"^[\(（]?\s*(?:[কখগঘA-Da-d1-4১-৪])\s*[\)）.।:：-]\s*", "", body)
    for idx, opt in enumerate(options, start=1):
        if plain and (plain == normalize_ws(opt) or plain in normalize_ws(opt)
                      or normalize_ws(opt) in plain):
            return idx
    return None


def parse_question_page(html: str, page_url: str) -> dict | None:
    """Parse a standalone Live MCQ question page (when one exists)."""
    soup = BeautifulSoup(html, "lxml")
    block = soup.select_one("div.qc")
    if block is None:
        return None
    return _parse_block(block, 1, page_url)
