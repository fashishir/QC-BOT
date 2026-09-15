# SSC Archive Bot

A production-grade, **ethical** Python web scraper that discovers, downloads, and
archives **publicly available** Bangladesh SSC (Secondary School Certificate)
board question papers (2005-2026) from all education boards - Dhaka, Chattogram,
Rajshahi, Khulna, Barishal, Sylhet, Rangpur, Mymensingh, Cumilla, Madrasah, and
Technical/Vocational.

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
# full pipeline: crawl -> download -> extract text (-> OCR if enabled)
python -m ssc_scraper scrape
python -m ssc_scraper scrape --source my_board_site --limit 50   # safer partial run

# individual steps
python -m ssc_scraper extract_text [--force] [--limit N]
python -m ssc_scraper ocr [--limit N]

# reporting
python -m ssc_scraper report          # reports/dashboard.json + .csv
python -m ssc_scraper check_missing   # reports/missing_combinations.csv + .json
python -m ssc_scraper export_csv      # reports/papers_export.csv
```

Every command is **idempotent and resumable** - running it again skips URLs and
files that were already processed.

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

python -m ssc_scraper scrape --source <name> --limit 50   # crawl + download + process
python -m ssc_scraper extract_text   # text extraction + metadata enrichment
python -m ssc_scraper report         # dashboard
python -m ssc_scraper check_missing  # missing-data matrix
