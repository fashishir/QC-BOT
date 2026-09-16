"""
Bangladesh Board Question Scraper - sattacademy.com
====================================================
Collects ALL SSC + HSC board exam questions (MCQ + Written) from:
  https://sattacademy.com/board-exams

Saves everything to:
  - SQLite database: board_questions.db
  - JSON files:      questions_output/
  - CSV report:      questions_output/report.csv

Usage:
  python scraper.py              # scrape everything (all boards, years, subjects)
  python scraper.py --year 2024  # one year only
  python scraper.py --limit 10   # test: first 10 exams only
  python scraper.py --class ssc  # SSC only
  streamlit run app.py           # view in browser
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
from urllib.parse import quote, urljoin

# Force UTF-8 output on Windows to handle Bangla text
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
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Referer": "https://sattacademy.com/board-exams",
}

DELAY = 2.0          # seconds between requests (polite)
TIMEOUT = 30         # seconds per request
MAX_RETRIES = 3      # retries on failure

# All class levels
CLASS_SLUGS = {
    "ssc":    "নবম-দশম-শ্রেণি-মাধ্যমিক",
    "dakhil": "নবম-দশম-শ্রেণি-দাখিল",
    "hsc":    "একাদশ-দ্বাদশ-শ্রেণি",
}

# All boards
BOARDS = {
    "ঢাকা-বোর্ড":              "dhaka",
    "রাজশাহী-বোর্ড":            "rajshahi",
    "চট্টগ্রাম-বোর্ড":          "chattogram",
    "সিলেট-বোর্ড":              "sylhet",
    "যশোর-বোর্ড":              "jessore",
    "কুমিল্লা-বোর্ড":            "cumilla",
    "দিনাজপুর-বোর্ড":            "dinajpur",
    "বরিশাল-বোর্ড":              "barishal",
    "ময়মনসিংহ-বোর্ড":            "mymensingh",
    "মাদ্রাসা-শিক্ষা-বোর্ড":    "madrasah",
    "কারিগরি-শিক্ষা-বোর্ড":    "technical",
    "সকল-বোর্ড":               "combined",
}

YEARS = list(range(2015, 2027))   # 2015 → 2026

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
            (remote_id, class_key, board, board_bn, year, exam_name, subject,
             mcq_url, written_url, mcq_count, cq_count, status, scraped_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(mcq_url) DO UPDATE SET
            status=excluded.status,
            scraped_at=excluded.scraped_at,
            mcq_count=coalesce(excluded.mcq_count, mcq_count),
            cq_count=coalesce(excluded.cq_count, cq_count),
            subject=coalesce(excluded.subject, subject)
    """, [
        exam.get("remote_id"), exam.get("class_key"), exam.get("board"),
        exam.get("board_bn"), exam.get("year"), exam.get("exam_name"),
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
    """Polite fetcher with delay + retry. Returns HTML text or None."""
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
                wait_s = 30
                warn(f"Rate limited (429). Waiting {wait_s}s...")
                time.sleep(wait_s)
            elif r.status_code >= 500:
                warn(f"Server error ({r.status_code}) on attempt {attempt}: {url}")
                time.sleep(5 * attempt)
            else:
                warn(f"Unexpected status {r.status_code}: {url}")
                return None
        except requests.RequestException as exc:
            warn(f"Request failed attempt {attempt}/{MAX_RETRIES}: {exc}")
            time.sleep(5 * attempt)
    err(f"All retries failed: {url}")
    return None

# ─────────────────────────── Parsers ──────────────────────────────────────────

def qp(text: str) -> str:
    """Percent-encode a Bangla URL segment."""
    return quote(text, safe="")


def listing_url(class_key: str, board_bn: str, year: int) -> str:
    slug = CLASS_SLUGS[class_key]
    return f"{BASE_URL}/board-exams/{qp(slug)}?board={qp(board_bn)}&year={year}"


def parse_listing(html_text: str, page_url: str) -> list[dict]:
    """Extract exam cards from a listing page."""
    soup = BeautifulSoup(html_text, "lxml")
    exams = []
    for card in soup.select("div.loginAlertModal"):
        mcq_url = (card.get("data-mcq-url") or "").strip()
        if not mcq_url:
            continue
        written_url = (card.get("data-written-url") or "").strip() or None
        # fallback: look for sibling anchors
        if not written_url:
            parent = card.find_parent()
            if parent:
                hrefs = [urljoin(page_url, a["href"])
                         for a in parent.find_all("a", href=True)]
                wr = [h for h in hrefs if h.rstrip("/").endswith("/written")]
                if wr:
                    written_url = wr[0]

        # MCQ/CQ counts from badge text
        scope = card.find_parent() or card
        badge = scope.get_text(separator=" ", strip=True)
        mcq_m = re.search(r"MCQ\s+(\d{1,3})(?!\d)", badge)
        cq_m  = re.search(r"(?<![A-Z])CQ\s+(\d{1,3})(?!\d)", badge)
        mcq_n = int(mcq_m.group(1)) if mcq_m else None
        cq_n  = int(cq_m.group(1))  if cq_m  else None

        try:
            year = int(card.get("data-year") or 0) or None
        except (TypeError, ValueError):
            year = None

        exam_name = (card.get("data-exam_name") or "").strip()
        exams.append({
            "remote_id":   card.get("data-id"),
            "exam_name":   exam_name,
            "year":        year,
            "mcq_url":     mcq_url,
            "written_url": written_url,
            "mcq_count":   mcq_n,
            "cq_count":    cq_n,
        })
    return exams


def parse_mcq_page(html_text: str, page_url: str) -> list[dict]:
    """Parse all MCQ questions from an exam page (page 1 only)."""
    soup = BeautifulSoup(html_text, "lxml")
    questions = []

    cards = [c for c in soup.select("div.card") if c.select_one("span.question-span")]
    for num, card in enumerate(cards, 1):
        # Stem text
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
            # fallback: green check-circle icon
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
    """Parse written/CQ questions from an exam page."""
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
            "answer":        None,       # CQ answers are login-gated
            "source_url":    href,
            "remote_id":     q_id_m.group(1) if q_id_m else None,
        })
    return questions


def has_pagination(html_text: str) -> bool:
    """True when the page has ?page= links (more pages exist)."""
    soup = BeautifulSoup(html_text, "lxml")
    return bool(soup.find("a", href=re.compile(r"[?&]page=\d+")))

# ─────────────────────────── Exporter ─────────────────────────────────────────

def save_json(exam: dict, questions: list[dict]) -> None:
    """Save exam questions to a JSON file."""
    OUT_DIR.mkdir(exist_ok=True)
    board = (exam.get("board") or "unknown").replace("/", "-")
    year  = exam.get("year") or "unknown"
    name  = re.sub(r'[^\w\s-]', '', exam.get("exam_name") or "exam")[:60].strip()
    fname = f"{board}_{year}_{name}.json".replace(" ", "_")
    path  = OUT_DIR / fname
    data  = {"exam": exam, "questions": questions}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv_report(conn: sqlite3.Connection) -> None:
    """Write a summary CSV of all exams + question counts."""
    OUT_DIR.mkdir(exist_ok=True)
    rows = conn.execute("""
        SELECT e.id, e.class_key, e.board, e.year, e.exam_name, e.subject,
               e.status, e.mcq_count, e.cq_count,
               COUNT(CASE WHEN q.question_type='mcq'     THEN 1 END) as mcq_scraped,
               COUNT(CASE WHEN q.question_type='written' THEN 1 END) as cq_scraped
        FROM exams e
        LEFT JOIN questions q ON q.exam_id = e.id
        GROUP BY e.id
        ORDER BY e.board, e.year, e.exam_name
    """).fetchall()
    path = OUT_DIR / "report.csv"
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "level", "board", "year", "exam_name", "subject",
                         "status", "mcq_total", "cq_total",
                         "mcq_scraped", "cq_scraped"])
        for r in rows:
            writer.writerow(list(r))
    log(f"CSV report written → {path}  ({len(rows)} exams)")

# ─────────────────────────── Main Scraper ─────────────────────────────────────

def scrape(class_keys: list[str], years: list[int],
           limit: int | None = None, skip_done: bool = True) -> None:
    conn = open_db()
    session = requests.Session()
    session.headers.update(HEADERS)

    total_exams = 0
    total_qs    = 0

    # Count already done exams to track progress
    done_count = 0

    log("=" * 60)
    log("Bangladesh Board Question Scraper — Starting")
    log(f"  Levels : {class_keys}")
    log(f"  Years  : {years[0]}–{years[-1]}")
    log(f"  Boards : {len(BOARDS)}")
    log(f"  Limit  : {limit or 'unlimited'}")
    log("=" * 60)

    for class_key in class_keys:
        for board_bn, board_en in BOARDS.items():
            for year in years:
                if limit is not None and total_exams >= limit:
                    log(f"Limit of {limit} exams reached — stopping.")
                    _finish(conn, total_exams, total_qs)
                    return

                url = listing_url(class_key, board_bn, year)
                log(f"Listing: {class_key} | {board_en} | {year} -> {url}")

                html_text = fetch(url, session)
                if html_text is None:
                    warn(f"  Failed to fetch listing, skipping.")
                    continue

                exams = parse_listing(html_text, url)
                if not exams:
                    log(f"  No exams found for {board_en} {year} {class_key}")
                    continue

                log(f"  Found {len(exams)} exam(s)")
                for exam in exams:
                    if limit is not None and total_exams >= limit:
                        break

                    exam["class_key"] = class_key
                    exam["board"]     = board_en
                    exam["board_bn"]  = board_bn

                    exam_id = upsert_exam(conn, exam)
                    exam["id"] = exam_id

                    # Check if already fully scraped
                    row = conn.execute(
                        "SELECT status FROM exams WHERE id=?", (exam_id,)
                    ).fetchone()
                    if skip_done and row and row["status"] == "completed":
                        q_count = conn.execute(
                            "SELECT COUNT(*) FROM questions WHERE exam_id=?",
                            (exam_id,)
                        ).fetchone()[0]
                        log(f"  [{exam['exam_name'][:40]}] Already done ({q_count} Qs) — skipping")
                        done_count += 1
                        total_exams += 1
                        continue

                    total_exams += 1
                    exam_qs = []

                    # --- Scrape MCQ ---
                    mcq_url = exam.get("mcq_url")
                    if mcq_url:
                        mcq_html = fetch(mcq_url, session)
                        if mcq_html:
                            mcq_qs = parse_mcq_page(mcq_html, mcq_url)
                            paged  = has_pagination(mcq_html)
                            log(f"  [MCQ] {exam['exam_name'][:40]}: {len(mcq_qs)} Qs"
                                + (" (truncated - pagination exists)" if paged else ""))
                            for q in mcq_qs:
                                q["exam_id"] = exam_id
                                save_question(conn, q)
                            exam_qs.extend(mcq_qs)
                            total_qs += len(mcq_qs)

                    # --- Scrape Written ---
                    written_url = exam.get("written_url")
                    if written_url:
                        wr_html = fetch(written_url, session)
                        if wr_html:
                            wr_qs = parse_written_page(wr_html, written_url)
                            log(f"  [CQ]  {exam['exam_name'][:40]}: {len(wr_qs)} Qs")
                            for q in wr_qs:
                                q["exam_id"] = exam_id
                                save_question(conn, q)
                            exam_qs.extend(wr_qs)
                            total_qs += len(wr_qs)

                    # Mark completed
                    mark_exam(conn, exam_id, "completed")

                    # Save JSON
                    save_json(exam, exam_qs)

    _finish(conn, total_exams, total_qs)


def _finish(conn: sqlite3.Connection, total_exams: int, total_qs: int) -> None:
    log("=" * 60)
    log(f"Done! Scraped {total_exams} exams, {total_qs} questions")
    write_csv_report(conn)
    stats = conn.execute(
        "SELECT status, COUNT(*) n FROM exams GROUP BY status"
    ).fetchall()
    for s in stats:
        log(f"  {s['status']:25s} : {s['n']}")
    log(f"Database  → {DB_PATH.resolve()}")
    log(f"Output    → {OUT_DIR.resolve()}")
    log("=" * 60)
    conn.close()

# ─────────────────────────── Entry Point ──────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bangladesh Board Question Scraper (sattacademy.com)"
    )
    parser.add_argument(
        "--class", dest="class_keys", default="ssc,dakhil,hsc",
        help="Comma-separated class keys: ssc, dakhil, hsc (default: all)"
    )
    parser.add_argument(
        "--year", type=int, default=None,
        help="Scrape only this year (e.g. 2024)"
    )
    parser.add_argument(
        "--board", default=None,
        help="Scrape only this board in English (e.g. dhaka, rajshahi)"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Stop after N exams (for testing)"
    )
    parser.add_argument(
        "--no-skip", action="store_true",
        help="Re-scrape even already-completed exams"
    )
    parser.add_argument(
        "--report-only", action="store_true",
        help="Only write the CSV report from existing DB data"
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
        print("Invalid --class values. Use: ssc, dakhil, hsc")
        sys.exit(1)

    years = [args.year] if args.year else YEARS

    # Filter boards if requested
    global BOARDS
    if args.board:
        BOARDS = {k: v for k, v in BOARDS.items() if v == args.board}
        if not BOARDS:
            print(f"Board '{args.board}' not found. Valid: {list(set(BOARDS.values()))}")
            sys.exit(1)

    scrape(
        class_keys=class_keys,
        years=years,
        limit=args.limit,
        skip_done=not args.no_skip,
    )


if __name__ == "__main__":
    main()
