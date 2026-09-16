# SSC + HSC Archive Bot

A production-grade, **ethical** Python web scraper that collects
**publicly available** Bangladesh SSC + HSC board questions (2015-2026),
subject-wise / board-wise / year-wise, MCQ + CQ(written), from
`https://sattacademy.com/board-exams` — plus a Streamlit filter UI that
mirrors the site's header (Level / Subject / Board / Type / Year / Search
+ Board Exams toggle + PDF export).

> **Ethics first.** This bot respects `robots.txt`, rate-limits every request,
> and **never** bypasses authentication, CAPTCHAs, paywalls, or anti-bot
> protection. Sources that block the bot are automatically flagged for manual
> review and skipped. Every stored file keeps full source attribution.

---

## Features

- **Modular architecture** - config, discovery, crawling, downloading,
  metadata extraction, deduplication, OCR, storage, and reporting are separate modules.
- **Config-driven sources** - add/remove websites in a YAML file; nothing is hard-coded.
- **Checkpoint / resume** - `crawl_state` + `papers.status` record exactly where
  each URL/file stands; re-running any command continues where it stopped.
- **Deduplication** - SHA-256 content hash plus normalized
  `(board, year, subject, paper_type)` metadata signature.
- **Bangla-aware metadata extraction** - English and Bangla keywords, Bangla
  numerals (`\u09e6-\u09ef`) converted for year detection.
- **Text extraction** - pdfplumber (primary) with PyMuPDF fallback; DOCX best-effort.
- **Optional OCR** - Tesseract with `ben+eng` language packs; fails soft to
  `ocr_pending` when Tesseract is unavailable.
- **Reports** - dashboard (JSON/CSV) and missing board-year-subject matrix.
- **PostgreSQL optional** - SQLite by default; switch via config.

## Project structure

```
config/sources.example.yaml   # example config (all sources disabled by default)
app.py                        # Streamlit filter UI (reads ssc_archive.db)
scraper.py                    # raw board-question scraper (board_questions.db)
sync_db.py                    # publish raw scrape -> ssc_archive.db (app DB)
ssc_scraper/
  cli.py                       # CLI: scrape | extract_text | ocr | report | check_missing | export_csv
  config.py                    # YAML loading/validation
  models.py                    # PaperRecord schema + status lifecycle
  db.py                        # SQLite/PostgreSQL storage layer
  robots.py                    # robots.txt compliance gate
  http_client.py               # polite HTTP: delays, retries, blocked->manual review
  crawler.py                   # checkpointed BFS discovery
  downloader.py                # streaming downloads, hashing, storage layout
  metadata.py                  # English+Bangla metadata extraction
  dedupe.py                    # hash + metadata duplicate detection
  text_extraction.py           # pdfplumber / PyMuPDF / DOCX text
  ocr.py                       # optional Tesseract OCR (ben+eng)
  reports.py                   # dashboards + missing-data report
  pipeline.py                  # orchestration with checkpoint/resume
  utils.py                     # hashing, paths, sanitization
  logging_setup.py             # console + rotating file logs
tests/                         # pytest unit tests (no network needed)
data/ logs/ reports/           # runtime artifacts
```

## Setup

Requires **Python 3.11+**.

```bash
# 1. (recommended) create a virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS

# 2. install dependencies
pip install -r requirements.txt

# 3. (optional) OCR support - install Tesseract with Bangla+English packs
#    Windows:  choco install tesseract        (then add install dir to PATH)
#    Debian:   apt install tesseract-ocr tesseract-ocr-ben tesseract-ocr-eng
#    macOS:    brew install tesseract tesseract-lang
```

### Configuration

Copy `config/sources.example.yaml` to your own file (or edit it in place).
**All sources ship disabled** - enable one only after *you* have reviewed that
site's terms of service and `robots.txt`:

```yaml
settings:
  user_agent: "SSC-Archive-Bot/1.0 (+educational archive; contact=you@example.com)"
  request_delay_seconds: 5.0     # per-host politeness delay (>= 1.0 enforced)
  max_pages_per_source: 500
  database:
    backend: sqlite              # or: postgres (+ pip install psycopg2-binary)
  ocr:
    enabled: false               # set true after installing Tesseract

sources:
  - name: my_board_site
    enabled: true                # <- your explicit opt-in
    base_url: https://www.example-board.gov.bd
    seed_urls: [https://www.example-board.gov.bd/question-archives]
    allow_domains: [www.example-board.gov.bd]
    keywords: [question, ssc]    # optional URL filter
    notes: null                  # e.g. "manual review: ..."
```

## Usage

```bash
# board-exam questions (SSC+HSC, 2015-2026, MCQ+written) — enable `sattacademy`
# in config/sources.example.yaml first, then:
python -m ssc_scraper scrape --source sattacademy --limit 20   # safe trial
python -m ssc_scraper scrape --source sattacademy              # full backfill (resumable)

# question-bank exports + reports
python -m ssc_scraper export_board_exams                        # reports/by_board_exam/... + coverage CSV
python -m ssc_scraper export_board_exams --board combined --year 2026
python -m ssc_scraper report          # reports/dashboard.json + .csv
python -m ssc_scraper check_missing   # reports/missing_combinations.csv + .json
python -m ssc_scraper export_csv      # reports/papers_export.csv

# filter UI (like the screenshots: SSC/Subject/Board/Type/Year/Search)
streamlit run app.py
```

Every command is **idempotent and resumable** - running it again skips URLs and
files that were already processed.

## Publishing updates to the live app

`scraper.py` writes the raw scrape to `board_questions.db` (git-ignored, local).
The Streamlit app reads `ssc_archive.db`, so a scrape is not visible online until
the two are synced and pushed:

```bash
python scraper.py                  # 1. scrape (board_questions.db + questions_output/)
python sync_db.py --dry-run        # 2. preview what would be published
python sync_db.py                  # 3. merge into ssc_archive.db (idempotent)
git add ssc_archive.db             # 4. publish -> triggers a Streamlit Cloud rebuild
git commit -m "data: refresh board question archive"
git push
```

On Windows the same flow is on the `run.bat` menu: **8** = sync only,
**9** = sync + commit + push (updates https://faqcbot.streamlit.app).

`sync_db.py` never deletes archive rows and maps fields like this:

| archive column | source |
| --- | --- |
| `board_exams.mcq_url` | `exams.mcq_url` (unique key, drives upsert) |
| `board_exams.subject` | `exams.subject`, falling back to `exam_name` when NULL (`--no-subject-from-name` to disable) |
| `board_exams.mcq_count` / `cq_count` | site totals from the raw DB, else the number of questions actually stored (`--page-1` scrapes are partial) |
| `board_exams.total_questions` | questions copied for that exam |
| `exam_questions.options_json` | normalised to `{"options": [...], "images": []}` so the UI renders options + answers |
| `exam_questions.answer` | `questions.correct_answer` (MCQ only; CQ answers are login-gated) |

Re-running the sync after a later scrape only touches the rows it re-reads, and it
finishes with a `wal_checkpoint(TRUNCATE)` + `VACUUM` so `ssc_archive.db` is
committed as a single self-contained file (no `-wal` / `-shm` side files).

## Data layout

```
data/{board}/{year}/{subject}/{paper_type}/{source_name}/{file_name}
```

Unknown facets are stored under `unknown/` and files are **relocated
automatically** once PDF text analysis fills in the metadata.

## Metadata schema (`papers` table)

`id, board, year, subject, paper_type, exam_code, set_code, shift, language,
file_url, source_page_url, source_name, downloaded_at, file_name, file_path,
file_hash, file_size, page_count, ocr_text, ocr_confidence, status,
missing_reason`

Status lifecycle: `discovered -> downloaded -> extracted -> ocr_done`, with
`duplicate | failed | ocr_pending | skipped` terminal states.

Board-exam statuses: `listed -> completed`, with `listing_truncated` /
`completed_truncated` when `?page=` pagination exists (robots-disallowed,
page-1 questions only — e.g. 10/30 MCQ on page 1). MCQ answers (`input[name=answer]`)
and stem/option images are stored when public; CQ answers stay `None` (login-gated).

## Legal & ethical compliance checklist

- [x] `robots.txt` checked before **every** crawl and download request
- [x] Per-host rate limiting with configurable polite delays
- [x] Identifying User-Agent with contact information
- [x] **No** CAPTCHA solving, login/paywall bypass, or anti-bot evasion anywhere
- [x] 401/403 responses -> source marked `manual_review`, never retried/bypassed
- [x] Only publicly accessible, unauthenticated content is collected
- [x] Full attribution stored per file (`file_url`, `source_page_url`, `source_name`)
- [x] Page and file-size caps to avoid burdening servers
- [x] Sources disabled by default; explicit human opt-in required

## Tests

```bash
python -m pytest tests/ -q
```

The tests cover utils, metadata (English + Bangla), the SQLite storage layer,
duplicate detection, config validation, and report generation - no network access needed.

## Disclaimer

Users are responsible for ensuring their use of this tool complies with the
terms of service of any site they configure, applicable copyright law, and fair
use/education exceptions in their jurisdiction. Question papers remain the
property of the respective education boards.

how to use it:

python -m ssc_scraper scrape --source sattacademy --limit 20   # trial: HSC/SSC board-exams
python -m ssc_scraper export_board_exams --board combined --year 2026
streamlit run app.py   # filter UI: Level/Subject/Board/Type/Year/Search + PDF
python -m ssc_scraper report         # dashboard
python -m ssc_scraper check_missing  # missing-data matrix

# scraper.py (raw questions) -> live app
python scraper.py                    # scrape into board_questions.db
python sync_db.py                    # merge into ssc_archive.db
git add ssc_archive.db; git commit -m "data: refresh"; git push   # live app rebuilds


 ### How to Run

  To scrape everything or specific targets, run any of the following commands:

    # Scrape ALL SSC & HSC Board Exams + Test Papers (2015-2026):
    python scraper.py

    # Scrape SSC only (2015-2026):
    python scraper.py --class ssc

    # Scrape HSC only (2015-2026):
    python scraper.py --class hsc

    # Scrape a specific year only (e.g. 2024):
    python scraper.py --year 2024

    # Scrape Board Exams only:
    python scraper.py --source board

    # Scrape Test Papers only:
    python scraper.py --source test

    # View all questions in the browser:
    streamlit run app.py


### How to Run PDF Exports: 

  • Export ALL collected exams to PDF:
    python export_pdf.py

  • Export SSC exams only:
    python export_pdf.py --class ssc

  • Export HSC exams only:
    python export_pdf.py --class hsc

  • Export a specific year (e.g. 2025):
    python export_pdf.py --year 2025

  • Export only Board Exams or Test Papers:
    python export_pdf.py --source board-exam
    python export_pdf.py --source test-paper