"""Collection pipelines for SattAcademy and approved Live MCQ pages."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import yaml

from .config import Settings
from .db import Database
from .http_client import PoliteHttpClient
from .livemcq import parse_solution_page, parse_solution_sections
from .logging_setup import get_logger
from .normalize import normalize_ws, now_iso
from .sattacademy_jobs import (
    HUB_URL,
    infer_institution,
    parse_category,
    parse_exam_questions,
    parse_hub,
)

log = get_logger("pipeline")

LIVEMCQ_PERMISSION_NOTE = (
    "Public Live MCQ solution page. robots.txt publishes a content signal "
    "ai-train=no, use=reference; the page was retrieved for reference/archival "
    "with attribution. User-approved source for this project."
)


class HtmlCache:
    """Small on-disk HTML cache for resume-safe, polite re-runs."""

    def __init__(self, root: str | Path | None):
        self.root = Path(root) if root else None

    def path_for(self, source: str, key: str) -> Path | None:
        if self.root is None:
            return None
        # Bengali category slugs contain no ASCII letters. Sanitizing them
        # directly collapses every category onto the same filename, so keep
        # a readable prefix and append a hash of the full key for uniqueness.
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", key)[:60].strip("_") or "page"
        return self.root / source / f"{safe}_{digest}.html"

    def read(self, source: str, key: str) -> str | None:
        path = self.path_for(source, key)
        if path and path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
        return None

    def write(self, source: str, key: str, text: str) -> None:
        path = self.path_for(source, key)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def fetch_html(client: PoliteHttpClient, cache: HtmlCache, source: str,
               key: str, url: str, *, refresh: bool = False) -> tuple[str | None, str | None]:
    """Fetch a page through the robots-aware client, with optional cache."""
    if not refresh:
        cached = cache.read(source, key)
        if cached:
            return cached, None
    result = client.fetch(url)
    if not result.ok:
        seen = result.status_code or "network"
        return None, f"{seen}: {result.error or url}"
    cache.write(source, key, result.text)
    return result.text, None


def scrape_sattacademy(db: Database, client: PoliteHttpClient, settings: Settings,
                       *, cache_dir: str | Path | None = "data/raw_html",
                       limit_categories: int | None = None,
                       limit_exams: int | None = None,
                       refresh: bool = False) -> dict[str, Any]:
    """Scrape all 40 categories, page 1 only, and store 2025-2026 MCQ sets."""
    cache = HtmlCache(cache_dir)
    run_id = db.start_run("sattacademy", notes="page-1-only public scrape")
    errors = 0
    categories = []
    exams_seen = 0
    exams_kept = 0
    questions_total = 0
    answers_total = 0

    hub_html, error = fetch_html(client, cache, "sattacademy", "hub", HUB_URL, refresh=refresh)
    if hub_html is None:
        db.finish_run(run_id, status="failed", errors=1, notes=error)
        raise RuntimeError(f"Could not fetch SattAcademy hub: {error}")

    categories = parse_hub(hub_html)
    log.info("SattAcademy: %d categories discovered", len(categories))
    if limit_categories:
        categories = categories[:limit_categories]

    exam_budget = limit_exams
    for category in categories:
        cat_id = db.upsert_category(
            category["slug"], category["name"],
            category["display_order"], category["source_url"],
        )
        page_html, error = fetch_html(
            client, cache, "sattacademy", f"category_{category['slug']}",
            category["source_url"], refresh=refresh,
        )
        if page_html is None:
            log.warning("Category failed: %s (%s)", category["name"], error)
            errors += 1
            continue

        exams = parse_category(page_html, category["source_url"])
        exams_seen += len(exams)
        log.info("Category %s: %d exam(s) in 2025-2026", category["name"], len(exams))
        for exam in exams:
            if exam_budget is not None and exam_budget <= 0:
                break
            try:
                used_source_id = str(exam["subcat_id"])
                existing = db.find_exam("sattacademy", used_source_id)
                prev_status = existing["coverage_status"] if existing else None
                prev_total = existing["total_questions"] if existing else None
                exam_id = db.upsert_exam({
                    "source": "sattacademy",
                    "source_id": used_source_id,
                    "exam_name": exam["exam_name"],
                    "institution": infer_institution(category["name"], exam["exam_name"]),
                    "post_name": None,
                    "exam_date": exam["exam_date"],
                    "year": exam["year"],
                    "exam_type": "mcq",
                    "total_questions": exam["total_questions"] or prev_total,
                    "collected_questions": 0,
                    "answered_questions": 0,
                    "coverage_status": prev_status if prev_status in
                        ("full", "partial_pdf") else "fallback_15",
                    "is_partial": 1,
                    "partial_reason": "public_page_limit",
                    "source_url": exam["source_url"],
                    "content_hash": None,
                    "status": "published",
                })
                db.add_exam_category(exam_id, cat_id)

                # Never replace an approved full set with the 15-question fallback.
                if prev_status in ("full", "partial_pdf"):
                    exams_kept += 1
                    if exam_budget is not None:
                        exam_budget -= 1
                    continue

                exam_html, error = fetch_html(
                    client, cache, "sattacademy", f"exam_{exam['subcat_id']}",
                    exam["source_url"], refresh=refresh,
                )
                if exam_html is None:
                    log.warning("Exam failed: %s (%s)", exam["exam_name"], error)
                    errors += 1
                    continue

                questions = parse_exam_questions(exam_html, exam["source_url"])
                inserted = db.replace_questions(exam_id, questions)
                questions_total += inserted
                answers_total += sum(1 for q in questions if q.get("answer_index"))
                if prev_status not in ("full", "partial_pdf"):
                    db.conn.execute(
                        "UPDATE job_exams SET coverage_status='fallback_15', "
                        "partial_reason='public_page_limit' WHERE id=?",
                        (exam_id,),
                    )
                    db.conn.commit()
                    db.recount_exam(exam_id)
                exams_kept += 1
                if exam_budget is not None:
                    exam_budget -= 1
            except Exception as exc:  # keep the run going, report later
                errors += 1
                log.exception("Exam import failed: %s (%s)", exam.get("exam_name"), exc)

    db.finish_run(
        run_id,
        categories=len(categories),
        exams_seen=exams_seen,
        exams_2025_26=exams_kept,
        questions=questions_total,
        answers=answers_total,
        errors=errors,
        status="ok" if errors == 0 else "partial",
        notes=f"kept {exams_kept} exams; {errors} errors",
    )
    return {
        "run_id": run_id,
        "categories": len(categories),
        "exams_seen": exams_seen,
        "exams_kept": exams_kept,
        "questions": questions_total,
        "answers": answers_total,
        "errors": errors,
    }


def load_livemcq_config(path: str | Path) -> list[dict]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8-sig")) or {}
    pages = data.get("pages") or []
    if not isinstance(pages, list):
        raise ValueError("livemcq config: 'pages' must be a list")
    for page in pages:
        for key in ("key", "url"):
            if not page.get(key):
                raise ValueError(f"livemcq config entry missing {key!r}: {page}")
        if not page.get("match_all") and not page.get("create_exam"):
            raise ValueError(
                f"livemcq config entry needs match_all or create_exam: {page}"
            )
    return pages


def _matches_exam(exam_name: str, page: dict) -> bool:
    haystack = normalize_ws(exam_name)
    if not all(normalize_ws(token) in haystack for token in page.get("match_all") or []):
        return False
    if any(normalize_ws(token) in haystack for token in page.get("match_none") or []):
        return False
    return True


def import_livemcq(db: Database, client: PoliteHttpClient, pages: list[dict],
                   *, cache_dir: str | Path | None = "data/raw_html",
                   refresh: bool = False) -> dict[str, Any]:
    """Import approved Live MCQ solution pages and replace fallback sets."""
    cache = HtmlCache(cache_dir)
    run_id = db.start_run("livemcq", notes="approved public solution pages")
    errors = 0
    imported = 0
    total_questions = 0
    total_answers = 0
    details: list[dict] = []

    for page in pages:
        try:
            html, error = fetch_html(
                client, cache, "livemcq", page["key"], page["url"], refresh=refresh,
            )
            if html is None:
                log.warning("Live MCQ page failed: %s (%s)", page["key"], error)
                errors += 1
                continue
            if page.get("section_date"):
                sections = parse_solution_sections(html, page["url"])
                section = next(
                    (s for s in sections if s["date"] == page["section_date"]), None
                )
                if section is None:
                    log.warning(
                        "Live MCQ page %s has no section dated %s (found %s)",
                        page["key"], page["section_date"],
                        [s["date"] for s in sections],
                    )
                    errors += 1
                    continue
                questions = section["questions"]
                log.info(
                    "Live MCQ section %s (%s): %d question(s)",
                    page["key"], page["section_date"], len(questions),
                )
            else:
                parsed = parse_solution_page(html, page["url"])
                questions = parsed["questions"]
            if not questions:
                log.warning("Live MCQ page has no qc blocks: %s", page["key"])
                errors += 1
                continue

            target = _find_target_exam(db, page)
            if target is None and page.get("create_exam"):
                target = _create_livemcq_exam(db, page)
            if target is None:
                log.warning("No SattAcademy exam matched Live MCQ page %s", page["key"])
                errors += 1
                continue

            expected = int(page.get("total_questions") or target["total_questions"] or 0)
            inserted = db.replace_questions(target["id"], questions)
            answered = sum(1 for q in questions if q.get("answer_index") in (1, 2, 3, 4))
            covered = len(questions)
            status = "full" if expected and covered >= expected else "partial_pdf"
            reason = None if status == "full" else "source_missing_questions"
            db.conn.execute(
                """
                UPDATE job_exams SET
                    total_questions = ?, coverage_status = ?, is_partial = ?,
                    partial_reason = ?, source_url = ?, last_scraped_at = ?
                WHERE id = ?
                """,
                (expected or covered, status, 0 if status == "full" else 1, reason,
                 page["url"], now_iso(), target["id"]),
            )
            db.conn.commit()
            db.recount_exam(target["id"])

            db.record_document(
                target["id"],
                doc_type="solution_page",
                source_name="Live MCQ",
                source_url=page["url"],
                sha256=hashlib.sha256(html.encode("utf-8")).hexdigest(),
                page_count=None,
                license_status="approved",
                permission_note=LIVEMCQ_PERMISSION_NOTE,
                publish_allowed=True,
                parser_version="1",
            )
            imported += 1
            total_questions += inserted
            total_answers += answered
            details.append({
                "key": page["key"], "exam": target["exam_name"],
                "questions": inserted, "answers": answered, "status": status,
            })
            log.info("Live MCQ %s -> %s (%d q, %d answered, %s)",
                     page["key"], target["exam_name"], inserted, answered, status)
        except Exception as exc:
            errors += 1
            log.exception("Live MCQ import failed: %s (%s)", page.get("key"), exc)

    db.finish_run(
        run_id,
        exams_2025_26=imported,
        questions=total_questions,
        answers=total_answers,
        errors=errors,
        status="ok" if errors == 0 else "partial",
        notes=f"imported {imported} pages; {errors} errors",
    )
    return {
        "run_id": run_id, "imported": imported, "questions": total_questions,
        "answers": total_answers, "errors": errors, "details": details,
    }


def _create_livemcq_exam(db: Database, page: dict):
    """Create/update a standalone exam for a Live MCQ-only solution page."""
    meta = page["create_exam"]
    expected = int(meta.get("total_questions") or page.get("total_questions") or 0)
    exam_id = db.upsert_exam({
        "source": "livemcq",
        "source_id": page["key"],
        "exam_name": meta["exam_name"],
        "institution": meta.get("institution"),
        "post_name": meta.get("post_name"),
        "exam_date": meta["exam_date"],
        "year": meta.get("year") or int(meta["exam_date"][:4]),
        "exam_type": "mcq",
        "total_questions": expected,
        "collected_questions": 0,
        "answered_questions": 0,
        "coverage_status": "partial_pdf",
        "is_partial": 1,
        "partial_reason": "source_missing_questions",
        "source_url": page["url"],
        "content_hash": None,
        "status": "published",
    })
    category = meta.get("category")
    if category:
        category_id = db.upsert_category(
            category["slug"], category["name"],
            int(category.get("display_order") or 0),
            category.get("source_url") or page["url"],
        )
        db.add_exam_category(exam_id, category_id)
    return db.get_exam(exam_id)


def _find_target_exam(db: Database, page: dict):
    # Explicit source_id wins so two same-date exams (e.g. 48th BCS
    # medical/dental) cannot be matched arbitrarily.
    source_id = page.get("sattacademy_source_id")
    if source_id:
        target = db.find_exam("sattacademy", str(source_id))
        if target is not None:
            return target
        log.warning(
            "Live MCQ %s: SattAcademy source_id %s not found; falling back to name match",
            page.get("key"), source_id,
        )

    # Only attempt name matching if match_all tokens are explicitly provided.
    # If the page relies on create_exam, we should not match arbitrarily.
    if not page.get("match_all"):
        return None

    exams = db.conn.execute(
        "SELECT * FROM job_exams WHERE source='sattacademy' ORDER BY exam_date DESC"
    ).fetchall()
    for exam in exams:
        if _matches_exam(exam["exam_name"], page):
            return exam
    return None
