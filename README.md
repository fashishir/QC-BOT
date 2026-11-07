# চাকরি পরীক্ষার MCQ প্রশ্নব্যাংক (২০২৫–২০২৬)

A Bangladesh **job-exam MCQ question bank** with public answers, covering
2025–2026 exams across all 40 SattAcademy job categories: BCS, NTRCA,
Judiciary/BJS, ATEO, banks, ministries, forces, and more.

The Streamlit app reads only the validated `job_archive.db`. Every question is
shown with its source and coverage status; answers that are not published at
the source are explicitly marked **উত্তর প্রকাশিত হয়নি** — they are never guessed.

---

## Sources

| Source | Role | What is collected |
|---|---|---|
| **SattAcademy** (`sattacademy.com`) | fallback | Public page 1 of each exam: up to 15 MCQs with answers |
| **Live MCQ** (`web.livemcq.com`) | primary full sets | Approved public solution pages that embed the complete MCQ set as HTML |
| **JobsNoticeBD** (`jobsnoticebd.com`) | audited, not used | 2025–2026 solution pages are image-only; excluded rather than OCR-guessed |

No other third-party source is used. Biddabari and EduDaily24 are explicitly
rejected (token-gated / bot-blocked).

### Compliance

- `robots.txt` is checked before every request.
- SattAcademy pagination (`/*?page=*`, `/*&page=*`) is **never** followed;
  only page 1 is collected.
- No login, paywall, CAPTCHA, download-token, or anti-bot bypass.
- 401/403 responses stop the request and are reported, never retried.
- Per-host delay (default 2 seconds) and identifying User-Agent.
- Only questions, options, and published answers are stored; explanations are
  discarded and never exported.
- Source name and link appear in the app and in every export.

---

## Project structure

```text
job_scraper/
  __init__.py
  __main__.py
  cli.py                 # scrape | import-livemcq | publish | stats | report
  config.py              # YAML settings
  models.py              # exam/question records
  normalize.py           # Bangla digits, dates, option labels, hashes
  db.py                  # schema, upserts, validation, atomic publish
  http_client.py         # robots-aware, rate-limited HTTP
  robots.py              # robots.txt gate
  logging_setup.py       # console + rotating file logs
  sattacademy_jobs.py    # hub/category/exam parsers
  livemcq.py             # Live MCQ div.qc parser
  pipeline.py            # SattAcademy + Live MCQ collection flows
  export.py              # CSV / printable HTML / PDF
app.py                   # Streamlit UI (job_archive.db only)
scraper.py               # thin CLI wrapper
sync_db.py               # publish raw -> job_archive.db
export_pdf.py            # PDF/CSV CLI
run.bat                  # Windows menu
config/job_sources.yaml  # source settings
config/livemcq_pages.yaml# approved Live MCQ pages + matching rules
tests/                   # parser, DB/publish, export, app tests
```

### Databases

- `job_questions.db` — raw/local scrape store, git-ignored.
- `job_archive.db` — validated, publishable archive, committed for the app.

The app never falls back to the raw DB or to any old SSC/HSC database.

---

## Setup

Requires Python 3.11+.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

`weasyprint` also needs Pango/HarfBuzz system libraries. On Streamlit Cloud
they are installed from `packages.txt`; locally, use the official WeasyPrint
installation notes if PDF rendering is unavailable. If WeasyPrint cannot
render, exports fall back to printable HTML.

---

## Usage

```bash
# 1. scrape all 40 SattAcademy categories (page 1 only)
python -m job_scraper scrape

# 2. import approved Live MCQ full sets
python -m job_scraper import-livemcq

# 3. validate and build the app archive
python sync_db.py

# 4. run the app
streamlit run app.py

# coverage report
python -m job_scraper report

# exports
python export_pdf.py --with-answers
python export_pdf.py --with-answers --csv pdf_exports/questions.csv
python export_pdf.py --year 2025 --with-answers
python export_pdf.py --category "বিসিএস প্রিলিমিনারি" --with-answers
```

Useful trial flags:

```bash
python -m job_scraper scrape --limit-categories 2 --limit-exams 5
python -m job_scraper stats
python -m job_scraper stats --archive
```

Re-runs are resume-safe: fetched HTML is cached under `data/raw_html/`
(git-ignored), and an approved Live MCQ full set is never overwritten by the
15-question SattAcademy fallback.

---

## Coverage semantics

| Status | Meaning |
|---|---|
| `full` | The approved source set matches the declared exam total |
| `partial_pdf` | A full-set source was imported but is missing some questions |
| `fallback_15` | Only SattAcademy's public 15 MCQs are available |
| `missing` | No questions; excluded from the archive |

The UI shows these as **পূর্ণ**, **আংশিক**, **ফলব্যাক ১৫**, and **অনুপলব্ধ**.
Partial exams always carry a visible notice; the app never claims a full set
when the source is incomplete.

### Why some exams are partial

SattAcademy publicly renders 15 questions per exam page. Further pages exist
but are disallowed by `robots.txt`, so they are not collected. Live MCQ full
sets are used where an approved page exposes the whole set as HTML; image-only
or answer-less pages are not imported.

---

## Database schema

- `job_categories` — the 40 job categories.
- `job_exams` — exam metadata, year (2025/2026 constraint), coverage counts,
  source, and status.
- `job_exam_categories` — many-to-many exam/category mapping.
- `job_questions` — four options, answer index/text, answer status, review
  status, images, hashes. `explanation` stays `NULL`.
- `job_documents` — third-party source/provenance, licence status,
  `publish_allowed`, SHA-256, and permission note.
- `scrape_runs`, `archive_meta` — run history and build metadata.

### Publish gates

`sync_db.py` / `job_scraper publish` rebuilds the archive atomically and
excludes:

- exams outside 2025–2026;
- third-party exams without an approved, publishable document;
- questions marked `needs_review` or `rejected`;
- all explanation text.

It fails on an empty archive (unless `--allow-empty`), invalid answer indexes,
invalid years, or any published explanation.

---

## Tests

```bash
pytest
```

Tests cover hub/category/exam parsing, answer extraction and missing-answer
marking, Live MCQ parsing, DB constraints and idempotent upserts, publish
gates, CSV/HTML export, and a Streamlit smoke test when `job_archive.db` exists.
No network access is required.

---

## Attribution and rights

Question content remains the property of its original source. This project
stores extracted questions/answers with attribution and links, and does not
redistribute source PDFs. Live MCQ's public pages carry a content signal of
`ai-train=no, use=reference`; they are used here as a cited reference archive
approved for this project. Remove any source on request.
