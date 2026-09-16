"""
Bangladesh Board Question Scraper - sattacademy.com
====================================================
Collects 2015-2026 SSC and HSC board exam questions (MCQ + Written/CQ)
and Test Papers from:
  - https://sattacademy.com/board-exams
  - https://sattacademy.com/test-papers

Saves everything to:
  - SQLite database: board_questions.db
  - JSON files:      questions_output/
  - CSV report:      questions_output/report.csv

Usage:
  python scraper.py                     # Scrape SSC + HSC Board Exams & Test Papers (2015-2026)
  python scraper.py --class ssc         # SSC only
  python scraper.py --class hsc         # HSC only
  python scraper.py --year 2024         # 2024 only
  python scraper.py --source board      # Board exams only
  python scraper.py --source test       # Test papers only
  python scraper.py --limit 10          # Test run: 10 exams only
  python scraper.py --report-only       # Export CSV summary from current DB
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse, parse_qs

# Force UTF-8 output on Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import requests
from bs4 import BeautifulSoup

# ─────────────────────────── Config ───────────────────────────────────────────

BASE_URL = "https://sattacademy.com"
DB_PATH = Path("board_questions.db")
OUT_DIR = Path("questions_output")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "bn,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

DELAY = 1.0          # seconds between requests (polite & responsive)
TIMEOUT = 30         # seconds per request
MAX_RETRIES = 3      # retries on failure

# Supported class categories
CLASS_SLUGS = {
    "ssc":    "নবম-দশম-শ্রেণি-মাধ্যমিক",
    "dakhil": "নবম-দশম-শ্রেণি-দাখিল",
    "hsc":    "একাদশ-দ্বাদশ-শ্রেণি",
}

# Bengali board name normalization
BOARD_MAP = {
    "ঢাকা বোর্ড": "dhaka",
    "ঢাকা-বোর্ড": "dhaka",
    "রাজশাহী বোর্ড": "rajshahi",
    "রাজশাহী-বোর্ড": "rajshahi",
    "চট্টগ্রাম বোর্ড": "chattogram",
    "চট্টগ্রাম-বোর্ড": "chattogram",
    "সিলেট বোর্ড": "sylhet",
    "সিলেট-বোর্ড": "sylhet",
    "যশোর বোর্ড": "jessore",
    "যশোর-বোর্ড": "jessore",
    "কুমিল্লা বোর্ড": "cumilla",
    "কুমিল্লা-বোর্ড": "cumilla",
    "দিনাজপুর বোর্ড": "dinajpur",
    "দিনাজপুর-বোর্ড": "dinajpur",
    "বরিশাল বোর্ড": "barishal",
    "বরিশাল-বোর্ড": "barishal",
    "ময়মনসিংহ বোর্ড": "mymensingh",
    "ময়মনসিংহ-বোর্ড": "mymensingh",
    "ময়মনসিংহ বোর্ড": "mymensingh",
    "ময়মনসিংহ-বোর্ড": "mymensingh",
    "মাদ্রাসা শিক্ষা বোর্ড": "madrasah",
    "মাদ্রাসা-শিক্ষা-বোর্ড": "madrasah",
    "কারিগরি শিক্ষা বোর্ড": "technical",
    "কারিগরি-শিক্ষা-বোর্ড": "technical",
    "সকল বোর্ড": "combined",
    "সকল-বোর্ড": "combined",
    "সমন্বিত বোর্ড": "combined",
    "সমন্বিত-বোর্ড": "combined",
    "সমন্বিত বোর্ড (সকল)": "combined",
}

YEARS = list(range(2015, 2027))   # 2015 -> 2026

# ─────────────────────────── Logging ──────────────────────────────────────────

def log(msg: str, level: str = "INFO") -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{level}] {msg}", flush=True)


def warn(msg: str) -> None:
    log(msg, "WARN")


def err(msg: str) -> None:
    log(msg, "ERROR")

# ─────────────────────────── Database ─────────────────────────────────────────

def open_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS exams (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            remote_id   TEXT,
            source_type TEXT DEFAULT 'board-exam', -- 'board-exam' or 'test-paper'
            class_key   TEXT,
            board       TEXT,
            board_bn    TEXT,
            year        INTEGER,
            exam_name   TEXT,
            subject     TEXT,
            mcq_url     TEXT UNIQUE,
            written_url TEXT,
            mcq_count   INTEGER,
            cq_count    INTEGER,
            status      TEXT DEFAULT 'listed',
            scraped_at  TEXT,
            CONSTRAINT uq_exam UNIQUE (mcq_url)
        );
        CREATE INDEX IF NOT EXISTS idx_exams_status ON exams (status);
        CREATE INDEX IF NOT EXISTS idx_exams_board  ON exams (board, year);
        CREATE INDEX IF NOT EXISTS idx_exams_class  ON exams (class_key, year);

        CREATE TABLE IF NOT EXISTS questions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_id         INTEGER REFERENCES exams(id),
            question_no     INTEGER,
            question_type   TEXT,
            question_text   TEXT,
            option_a        TEXT,
            option_b        TEXT,
            option_c        TEXT,
            option_d        TEXT,
            correct_answer  TEXT,
            options_json    TEXT,
            source_url      TEXT,
            scraped_at      TEXT,
            CONSTRAINT uq_q UNIQUE (exam_id, question_type, question_no)
        );
        CREATE INDEX IF NOT EXISTS idx_q_exam ON questions (exam_id);
    """)
    conn.commit()
    return conn


def upsert_exam(conn: sqlite3.Connection, exam: dict) -> int:
    conn.execute("""
        INSERT INTO exams
            (remote_id, source_type, class_key, board, board_bn, year, exam_name, subject,
             mcq_url, written_url, mcq_count, cq_count, status, scraped_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(mcq_url) DO UPDATE SET
            status=excluded.status,
            scraped_at=excluded.scraped_at,
            mcq_count=coalesce(excluded.mcq_count, mcq_count),
            cq_count=coalesce(excluded.cq_count, cq_count),
            subject=coalesce(excluded.subject, subject),
            board=coalesce(excluded.board, board),
            board_bn=coalesce(excluded.board_bn, board_bn),
            year=coalesce(excluded.year, year),
            source_type=coalesce(excluded.source_type, source_type)
    """, [
        exam.get("remote_id"), exam.get("source_type", "board-exam"), exam.get("class_key"),
        exam.get("board"), exam.get("board_bn"), exam.get("year"), exam.get("exam_name"),
        exam.get("subject"), exam.get("mcq_url") or "", exam.get("written_url"),
        exam.get("mcq_count"), exam.get("cq_count"),
        exam.get("status", "listed"), now(),
    ])
    conn.commit()
    row = conn.execute("SELECT id FROM exams WHERE mcq_url=?",
                       (exam.get("mcq_url") or "",)).fetchone()
    return row["id"]


def mark_exam(conn: sqlite3.Connection, exam_id: int, status: str) -> None:
    conn.execute("UPDATE exams SET status=? WHERE id=?", (status, exam_id))
    conn.commit()


def save_question(conn: sqlite3.Connection, q: dict) -> None:
    opts = q.get("options", [])
    a = opts[0].get("text", "") if len(opts) > 0 else ""
    b = opts[1].get("text", "") if len(opts) > 1 else ""
    c = opts[2].get("text", "") if len(opts) > 2 else ""
    d = opts[3].get("text", "") if len(opts) > 3 else ""
    conn.execute("""
        INSERT INTO questions
            (exam_id, question_no, question_type, question_text,
             option_a, option_b, option_c, option_d, correct_answer,
             options_json, source_url, scraped_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(exam_id, question_type, question_no) DO UPDATE SET
            question_text=excluded.question_text,
            option_a=excluded.option_a, option_b=excluded.option_b,
            option_c=excluded.option_c, option_d=excluded.option_d,
            correct_answer=excluded.correct_answer,
            options_json=excluded.options_json
    """, [
        q["exam_id"], q["question_no"], q["question_type"], q["question_text"],
        a, b, c, d, q.get("answer"),
        json.dumps(q.get("options", []), ensure_ascii=False),
        q.get("source_url"), now(),
    ])
    conn.commit()


def now() -> str:
    return datetime.now().isoformat()

# ─────────────────────────── HTTP ─────────────────────────────────────────────

_last_req: float = 0.0


def fetch(url: str, session: requests.Session) -> str | None:
    """Polite fetcher with delay and retry."""
    global _last_req
    wait = DELAY - (time.monotonic() - _last_req)
    if wait > 0:
        time.sleep(wait)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = session.get(url, headers=HEADERS, timeout=TIMEOUT)
            _last_req = time.monotonic()
            if r.status_code == 200:
                return r.text
            elif r.status_code in (401, 403):
                warn(f"Access denied ({r.status_code}): {url}")
                return None
            elif r.status_code == 429:
                wait_s = 20
                warn(f"Rate limited (429). Waiting {wait_s}s...")
                time.sleep(wait_s)
            elif r.status_code >= 500:
                warn(f"Server error ({r.status_code}) attempt {attempt}: {url}")
                time.sleep(3 * attempt)
            else:
                warn(f"Unexpected status {r.status_code}: {url}")
                return None
        except requests.RequestException as exc:
            warn(f"Request failed attempt {attempt}/{MAX_RETRIES}: {exc}")
            time.sleep(3 * attempt)
    err(f"All retries failed: {url}")
    return None

# ─────────────────────────── Parsers ──────────────────────────────────────────

def qp(text: str) -> str:
    """Percent-encode URL path segment."""
    return quote(text, safe="")


def normalize_board(board_text: str) -> tuple[str, str]:
    """Return (board_en, board_bn) from parsed string."""
    clean = board_text.strip().lstrip("|").strip()
    if clean in BOARD_MAP:
        return BOARD_MAP[clean], clean
    for k, v in BOARD_MAP.items():
        if k in clean:
            return v, clean
    return "other", clean


def parse_listing_page(html_text: str, page_url: str, default_class: str = "ssc", source_type: str = "board-exam") -> tuple[list[dict], int]:
    """
    Extract exam cards from a listing page and identify max page number.
    Returns (list of exam dicts, max_page).
    """
    soup = BeautifulSoup(html_text, "lxml")
    exams = []

    # Find maximum page number from pagination
    max_page = 1
    for a in soup.select("ul.pagination li a"):
        href = a.get("href") or ""
        m = re.search(r"[?&]page=(\d+)", href)
        if m:
            page_num = int(m.group(1))
            if page_num > max_page:
                max_page = page_num

    for card in soup.select("div.loginAlertModal"):
        mcq_url = (card.get("data-mcq-url") or "").strip()
        if not mcq_url:
            continue
        mcq_url = urljoin(page_url, mcq_url)

        # Card container holds additional details (board, year, CQ links)
        card_container = card.find_parent("div", class_="card") or card

        written_url = (card.get("data-written-url") or "").strip() or None
        if not written_url:
            for a in card_container.find_all("a", href=True):
                href = urljoin(page_url, a["href"])
                if href.rstrip("/").endswith("/written") or "/written" in href:
                    written_url = href
                    break

        # MCQ/CQ counts from badge or text
        badge = card_container.get_text(separator=" ", strip=True)
        mcq_m = re.search(r"MCQ\s*(\d{1,3})", badge)
        cq_m  = re.search(r"(?<![A-Z])CQ\s*(\d{1,3})", badge)
        mcq_n = int(mcq_m.group(1)) if mcq_m else None
        cq_n  = int(cq_m.group(1))  if cq_m  else None

        # Year
        try:
            year = int(card.get("data-year") or 0) or None
        except (TypeError, ValueError):
            year = None

        if not year:
            ym = re.search(r"\b(201\d|202\d)\b", badge)
            if ym:
                year = int(ym.group(1))

        exam_name = (card.get("data-exam_name") or "").strip()
        if not exam_name:
            h_link = card.select_one("a")
            exam_name = h_link.get_text(strip=True) if h_link else "Exam"

        # Board extraction
        board_bn = ""
        board_en = "other"
        board_m = re.search(r"\|\|\s*([^|]+বোর্ড(?:\s*\([^)]*\))?)", badge)
        if board_m:
            board_raw = board_m.group(1).strip()
            board_en, board_bn = normalize_board(board_raw)
        else:
            # Fallback check across badge text
            for b_k, b_v in BOARD_MAP.items():
                if b_k in badge:
                    board_en = b_v
                    board_bn = b_k
                    break

        # Class key check
        class_key = default_class
        sub_cat = (card.get("data-sub_cat") or "").strip()
        if "দাখিল" in sub_cat:
            class_key = "dakhil"
        elif "এইচএসসি" in sub_cat or "একাদশ" in sub_cat:
            class_key = "hsc"
        elif "এসএসসি" in sub_cat or "নবম" in sub_cat:
            class_key = "ssc"

        exams.append({
            "remote_id":   card.get("data-id"),
            "source_type": source_type,
            "class_key":   class_key,
            "exam_name":   exam_name,
            "subject":     exam_name,
            "board":       board_en,
            "board_bn":    board_bn,
            "year":        year,
            "mcq_url":     mcq_url,
            "written_url": written_url,
            "mcq_count":   mcq_n,
            "cq_count":    cq_n,
        })

    return exams, max_page


def parse_mcq_page(html_text: str, page_url: str) -> list[dict]:
    """Parse MCQ questions from an exam page."""
    soup = BeautifulSoup(html_text, "lxml")
    questions = []

    cards = [c for c in soup.select("div.card") if c.select_one("span.question-span")]
    for num, card in enumerate(cards, 1):
        stem_el = card.select_one("span.question-span.white-heading") \
                   or card.select_one("span.question-span")
        stem = stem_el.get_text(separator=" ", strip=True) if stem_el else ""

        # Stem images
        stem_imgs = []
        if stem_el:
            for img in stem_el.select("img"):
                src = img.get("src") or img.get("data-src") or ""
                if src:
                    stem_imgs.append(urljoin(page_url, src))
        for img in card.select(".card-header img"):
            src = img.get("src") or ""
            if src:
                abs_src = urljoin(page_url, src)
                if abs_src not in stem_imgs:
                    stem_imgs.append(abs_src)

        # Options
        labels = card.select(".reading-mode-data label") or card.select("label")
        options = []
        for idx, label in enumerate(labels, 1):
            opt_imgs = [urljoin(page_url, img.get("src", ""))
                        for img in label.select("img") if img.get("src")]
            options.append({
                "index":  idx,
                "text":   label.get_text(separator=" ", strip=True),
                "images": opt_imgs,
            })

        # Correct answer
        answer = None
        ans_inp = card.select_one('input[name="answer"]')
        if ans_inp and (ans_inp.get("value") or "").strip().isdigit():
            answer = str(int(ans_inp.get("value")))

        if answer is None:
            # Check for check-circle icon
            for idx, label in enumerate(labels, 1):
                parent_div = label.find_parent("div", class_=re.compile(r"col-md-6"))
                scope = parent_div if parent_div else label.parent
                if scope and scope.select_one(".fa-check-circle"):
                    answer = str(idx)
                    break

        questions.append({
            "question_no":   num,
            "question_type": "mcq",
            "question_text": stem,
            "images":        stem_imgs,
            "options":       options,
            "answer":        answer,
            "source_url":    page_url,
        })
    return questions


def parse_written_page(html_text: str, page_url: str) -> list[dict]:
    """Parse written / CQ questions from an exam page."""
    soup = BeautifulSoup(html_text, "lxml")
    questions = []
    num = 0
    for li in soup.find_all("li"):
        anchor = li.find("a", href=lambda h: h and "/question/" in h)
        if not anchor:
            continue
        text = anchor.get_text(separator=" ", strip=True)
        if not text:
            continue
        num += 1
        href = urljoin(page_url, anchor.get("href", ""))
        q_id_m = re.search(r"-(\d+)(?:/?)$", anchor.get("href", ""))
        images = [urljoin(page_url, img.get("src", ""))
                  for img in li.select("img") if img.get("src")]
        questions.append({
            "question_no":   num,
            "question_type": "written",
            "question_text": text,
            "images":        images,
            "options":       [],
            "answer":        None,
            "source_url":    href,
            "remote_id":     q_id_m.group(1) if q_id_m else None,
        })
    return questions

# ─────────────────────────── Exporter ─────────────────────────────────────────

def save_json(exam: dict, questions: list[dict]) -> None:
    """Save exam questions to a JSON file."""
    OUT_DIR.mkdir(exist_ok=True)
    board = (exam.get("board") or "unknown").replace("/", "-")
    year  = exam.get("year") or "unknown"
    source = exam.get("source_type") or "board"
    name  = re.sub(r'[^\w\s-]', '', exam.get("exam_name") or "exam")[:50].strip()
    fname = f"{source}_{board}_{year}_{name}.json".replace(" ", "_")
    path  = OUT_DIR / fname
    data  = {"exam": exam, "questions": questions}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv_report(conn: sqlite3.Connection) -> None:
    """Write summary CSV of all exams and question counts."""
    OUT_DIR.mkdir(exist_ok=True)
    rows = conn.execute("""
        SELECT e.id, e.source_type, e.class_key, e.board, e.year, e.exam_name, e.subject,
               e.status, e.mcq_count, e.cq_count,
               COUNT(CASE WHEN q.question_type='mcq'     THEN 1 END) as mcq_scraped,
               COUNT(CASE WHEN q.question_type='written' THEN 1 END) as cq_scraped
        FROM exams e
        LEFT JOIN questions q ON q.exam_id = e.id
        GROUP BY e.id
        ORDER BY e.year DESC, e.source_type, e.class_key, e.board
    """).fetchall()
    path = OUT_DIR / "report.csv"
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "source_type", "level", "board", "year", "exam_name", "subject",
                         "status", "mcq_total", "cq_total",
                         "mcq_scraped", "cq_scraped"])
        for r in rows:
            writer.writerow(list(r))
    log(f"CSV report written -> {path} ({len(rows)} exams)")

# ─────────────────────────── Main Scraper ─────────────────────────────────────

def scrape(
    class_keys: list[str],
    years: list[int],
    source_types: list[str],
    limit: int | None = None,
    skip_done: bool = True,
) -> None:
    conn = open_db()
    session = requests.Session()
    session.headers.update(HEADERS)

    total_exams = 0
    total_qs    = 0

    log("=" * 65)
    log("SattAcademy Question Scraper — SSC & HSC (2015-2026)")
    log(f"  Levels  : {class_keys}")
    log(f"  Years   : {min(years)} - {max(years)}")
    log(f"  Sources : {source_types}")
    log(f"  Limit   : {limit or 'unlimited'}")
    log("=" * 65)

    for source_type in source_types:
        endpoint = "board-exams" if source_type == "board-exam" else "test-papers"

        for class_key in class_keys:
            class_slug = CLASS_SLUGS[class_key]

            for year in sorted(years, reverse=True):
                if limit is not None and total_exams >= limit:
                    break

                # Scrape page 1 of (source, class, year)
                initial_url = f"{BASE_URL}/{endpoint}/{qp(class_slug)}?year={year}&page=1"
                log(f"Listing -> {source_type} | {class_key.upper()} | {year} | Page 1")

                html = fetch(initial_url, session)
                if not html:
                    continue

                exams, max_page = parse_listing_page(html, initial_url, default_class=class_key, source_type=source_type)
                log(f"  Page 1: found {len(exams)} exam(s) (Total pages: {max_page})")

                # Collect exams across all available pages for this combination
                all_discovered = list(exams)
                for page in range(2, max_page + 1):
                    if limit is not None and (total_exams + len(all_discovered)) >= limit:
                        break
                    p_url = f"{BASE_URL}/{endpoint}/{qp(class_slug)}?year={year}&page={page}"
                    log(f"  Fetching page {page}/{max_page}...")
                    p_html = fetch(p_url, session)
                    if p_html:
                        p_exams, _ = parse_listing_page(p_html, p_url, default_class=class_key, source_type=source_type)
                        all_discovered.extend(p_exams)

                # Now process each exam
                for exam in all_discovered:
                    if limit is not None and total_exams >= limit:
                        log(f"Limit of {limit} exams reached.")
                        _finish(conn, total_exams, total_qs)
                        return

                    exam_id = upsert_exam(conn, exam)
                    exam["id"] = exam_id

                    # Skip if already completed
                    row = conn.execute("SELECT status FROM exams WHERE id=?", (exam_id,)).fetchone()
                    if skip_done and row and row["status"] == "completed":
                        q_count = conn.execute(
                            "SELECT COUNT(*) FROM questions WHERE exam_id=?", (exam_id,)
                        ).fetchone()[0]
                        log(f"  [{exam['exam_name'][:35]}] Already done ({q_count} Qs) — skipping")
                        total_exams += 1
                        continue

                    total_exams += 1
                    exam_qs = []

                    # 1. Scrape MCQ page
                    mcq_url = exam.get("mcq_url")
                    if mcq_url:
                        mcq_html = fetch(mcq_url, session)
                        if mcq_html:
                            mcq_qs = parse_mcq_page(mcq_html, mcq_url)
                            log(f"  [MCQ] {exam['exam_name'][:35]}: {len(mcq_qs)} Qs")
                            for q in mcq_qs:
                                q["exam_id"] = exam_id
                                save_question(conn, q)
                            exam_qs.extend(mcq_qs)
                            total_qs += len(mcq_qs)

                    # 2. Scrape Written/CQ page
                    written_url = exam.get("written_url")
                    if written_url:
                        wr_html = fetch(written_url, session)
                        if wr_html:
                            wr_qs = parse_written_page(wr_html, written_url)
                            log(f"  [CQ]  {exam['exam_name'][:35]}: {len(wr_qs)} Qs")
                            for q in wr_qs:
                                q["exam_id"] = exam_id
                                save_question(conn, q)
                            exam_qs.extend(wr_qs)
                            total_qs += len(wr_qs)

                    # Mark completed & save JSON backup
                    mark_exam(conn, exam_id, "completed")
                    save_json(exam, exam_qs)

    _finish(conn, total_exams, total_qs)


def _finish(conn: sqlite3.Connection, total_exams: int, total_qs: int) -> None:
    log("=" * 65)
    log(f"Completed! Scraped {total_exams} exams, {total_qs} questions total.")
    write_csv_report(conn)
    stats = conn.execute(
        "SELECT status, COUNT(*) n FROM exams GROUP BY status"
    ).fetchall()
    for s in stats:
        log(f"  {s['status']:20s} : {s['n']}")
    log(f"Database -> {DB_PATH.resolve()}")
    log(f"Output   -> {OUT_DIR.resolve()}")
    log("=" * 65)
    conn.close()

# ─────────────────────────── Entry Point ──────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bangladesh Board & Test Paper Question Scraper (sattacademy.com)"
    )
    parser.add_argument(
        "--class", dest="class_keys", default="ssc,hsc,dakhil",
        help="Comma-separated class keys: ssc, hsc, dakhil (default: all)"
    )
    parser.add_argument(
        "--year", type=int, default=None,
        help="Scrape only this year (e.g. 2024)"
    )
    parser.add_argument(
        "--source", choices=["all", "board", "test"], default="all",
        help="Source: board (board-exams), test (test-papers), or all (default: all)"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Stop after N exams (useful for verification)"
    )
    parser.add_argument(
        "--no-skip", action="store_true",
        help="Re-scrape even already-completed exams"
    )
    parser.add_argument(
        "--report-only", action="store_true",
        help="Only generate CSV report from existing database"
    )
    args = parser.parse_args()

    if args.report_only:
        conn = open_db()
        write_csv_report(conn)
        conn.close()
        return

    class_keys = [k.strip() for k in args.class_keys.split(",")
                  if k.strip() in CLASS_SLUGS]
    if not class_keys:
        print("Invalid --class values. Use: ssc, hsc, dakhil")
        sys.exit(1)

    years = [args.year] if args.year else YEARS

    source_map = {
        "all": ["board-exam", "test-paper"],
        "board": ["board-exam"],
        "test": ["test-paper"],
    }
    source_types = source_map[args.source]

    scrape(
        class_keys=class_keys,
        years=years,
        source_types=source_types,
        limit=args.limit,
        skip_done=not args.no_skip,
    )


if __name__ == "__main__":
    main()
