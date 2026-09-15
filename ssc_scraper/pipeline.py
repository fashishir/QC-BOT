"""Pipeline orchestration with checkpoint/resume.

Runs the full flow per source: crawl -> download -> extract text &
enrich metadata -> optional OCR. Every step is resumable: crawl_state and
papers.status record exactly where each URL/file stands, so re-running a
command continues from where the previous one stopped.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .config import AppConfig
from . import sattacademy
from .crawler import Crawler
from .downloader import Downloader
from .http_client import PoliteHttpClient
from .logging_setup import get_logger
from .metadata import MetadataExtractor
from .models import PaperRecord
from .ocr import OCRUnavailable, ocr_pdf
from .reports import ReportGenerator
from .text_extraction import extract_doc_text, extract_pdf_text
from .utils import build_storage_path, now_iso, unique_path

log = get_logger("pipeline")


class ScraperPipeline:
    """End-to-end orchestration for the configured sources."""

    def __init__(self, config: AppConfig, db):
        self.config = config
        self.settings = config.settings
        self.db = db
        self.db.connect()
        self.db.create_schema()

        self.client = PoliteHttpClient(self.settings)
        self.crawler = Crawler(self.db, self.client, self.settings)
        self.extractor = MetadataExtractor()
        self.downloader = Downloader(self.db, self.client, self.settings,
                                     extractor=self.extractor)
        self.reports = ReportGenerator(self.db, self.settings)

    def close(self) -> None:
        self.client.close()
        self.db.close()

    # ---------------------------------------------------------------- scrape
    def scrape(self, source_name: str | None = None,
               limit: int | None = None) -> dict:
        started = now_iso()
        if source_name:
            source = self.config.get_source(source_name)
            if source is None:
                raise ValueError(f"Unknown source: {source_name!r}")
            sources = [source]
        else:
            sources = self.config.enabled_sources()
        if not sources:
            log.warning("No enabled sources in the config - nothing to do")

        summary: dict = {"sources": {}, "extracted": 0, "ocr": 0}
        for source in sources:
            log.info("=== Source: %s ===", source.name)
            if getattr(source, "adapter", "") == "sattacademy":
                summary["sources"][source.name] = {
                    "board_exams": self.scrape_board_exams(source, limit),
                }
                continue
            self.db.upsert_source(source.name, source.base_url, source.enabled,
                                  notes=source.notes)
            if source.notes and "manual review" in source.notes.lower():
                self.db.set_source_status(source.name, "manual_review",
                                          note=source.notes)

            crawl_stats = self.crawler.crawl_source(source)
            download_stats = self.download_source(source, limit)
            summary["sources"][source.name] = {
                "crawl": crawl_stats,
                "download": download_stats,
            }

        summary["extracted"] = self.extract_text()
        if self.settings.ocr.enabled:
            summary["ocr"] = self.run_ocr()

        self.db.log_run("scrape", started, summary)
        return summary

    # -------------------------------------------------------------- download
    def download_source(self, source, limit: int | None = None) -> dict:
        """Download every pending candidate for *source*."""
        stats = {"processed": 0, "duplicates": 0, "failed": 0}
        candidates = self.db.iter_crawl(source_name=source.name,
                                        statuses=["candidate"])
        if limit is not None:
            candidates = candidates[:limit]
        log.info("%d candidate document(s) for %r", len(candidates), source.name)
        for candidate in candidates:
            record = self.downloader.download_candidate(
                candidate["url"], source,
                found_on=candidate.get("found_on"),
                context=candidate.get("context") or "",
            )
            if record is None:
                stats["failed"] += 1
            elif record.status == "duplicate":
                stats["duplicates"] += 1
            else:
                stats["processed"] += 1
        return stats

    # ---------------------------------------------------------- extract text
    def extract_text(self, force: bool = False,
                     limit: int | None = None) -> int:
        """Extract PDF/DOCX text for downloaded papers, enriching metadata.

        Text is stored in the ocr_text column (direct extraction first;
        OCR replaces it later when the paper turns out to be scanned).
        Returns the number of papers processed.
        """
        statuses = ["downloaded"] + (["extracted"] if force else [])
        rows = self.db.iter_papers(statuses=statuses, has_file=True)
        if limit is not None:
            rows = rows[:limit]
        processed = 0
        for row in rows:
            path = Path(row["file_path"])
            if path.suffix.lower() == ".pdf":
                text, pages, method = extract_pdf_text(path)
            elif path.suffix.lower() in (".doc", ".docx"):
                text, pages, method = extract_doc_text(path)
            else:
                text, pages, method = "", None, "none"

            if method == "missing":
                self.db.update_paper(row["id"], status="failed",
                                     missing_reason="file missing on disk")
                continue
            if not text:
                # Likely a scanned paper - leave for the OCR step.
                updates: dict = {"status": "extracted"}
                if pages:
                    updates["page_count"] = pages
                self.db.update_paper(row["id"], **updates)
                log.info("No text layer in %s (method=%s) - OCR candidate",
                         path.name, method)
                processed += 1
                continue

            record = PaperRecord.from_row(row)
            record.merge_metadata(self.extractor.from_pdf_text(text))
            self._relocate_if_needed(row, record)

            updates = {
                k: v for k, v in record.to_dict().items()
                if k not in ("file_url", "status", "created_at", "updated_at", "id")
            }
            updates["ocr_text"] = text
            updates["page_count"] = pages if pages else record.page_count
            updates["status"] = "extracted"
            self.db.update_paper(row["id"], **updates)
            processed += 1
        log.info("Text extraction processed %d paper(s)", processed)
        return processed

    # -------------------------------------------------------------------- ocr
    def run_ocr(self, limit: int | None = None) -> int:
        """OCR scanned papers (little/no text). Fails soft to 'ocr_pending'."""
        ocr_cfg = self.settings.ocr
        if not ocr_cfg.enabled:
            log.info("OCR disabled in config - skipping")
            return 0

        candidates = [
            row for row in self.db.iter_papers(statuses=["extracted"])
            if len(row.get("ocr_text") or "") < ocr_cfg.min_text_chars_to_skip_ocr
        ]
        if limit is not None:
            candidates = candidates[:limit]
        processed = 0
        for row in candidates:
            path = Path(row["file_path"] or "")
            if path.suffix.lower() != ".pdf" or not path.exists():
                continue
            try:
                text, confidence, _pages = ocr_pdf(
                    path,
                    languages=ocr_cfg.languages,
                    max_pages=ocr_cfg.max_pages,
                    tesseract_cmd=ocr_cfg.tesseract_cmd,
                )
            except OCRUnavailable as exc:
                log.warning("OCR unavailable: %s", exc)
                self.db.update_paper(row["id"], status="ocr_pending",
                                     missing_reason=str(exc)[:500])
                break  # no point retrying every paper this run
            except Exception as exc:  # per-document OCR failure
                log.warning("OCR failed on %s: %s", path.name, exc)
                self.db.update_paper(row["id"], status="ocr_pending",
                                     missing_reason=f"ocr error: {exc}"[:500])
                continue

            if text:
                self.db.update_paper(row["id"], ocr_text=text,
                                     ocr_confidence=confidence,
                                     status="ocr_done")
                # OCR text may reveal metadata missed by the filename.
                record = PaperRecord.from_row(row)
                record.merge_metadata(self.extractor.from_pdf_text(text))
                self._relocate_if_needed(row, record)
                updates = {
                    k: v for k, v in record.to_dict().items()
                    if k in ("board", "year", "subject", "paper_type",
                             "set_code", "shift", "file_path", "file_name")
                }
                if updates:
                    self.db.update_paper(row["id"], **updates)
            else:
                self.db.update_paper(row["id"], status="ocr_pending",
                                     missing_reason="OCR produced no text")
            processed += 1
        log.info("OCR processed %d paper(s)", processed)
        return processed

    # ------------------------------------------------------- board exams
    def scrape_board_exams(self, source, limit: int | None = None) -> dict:
        """Collect question-bank exams: listing -> exam cards -> questions.

        Expectations per source.params:
          class_keys : ['ssc', 'dakhil', 'hsc']  (sattacademy.CLASS_SLUGS keys)
          board_slugs: list of Bangla board slugs (sattacademy.BOARD_SLUGS)
          years      : [2015..2026]
          question_types: ['mcq', 'written'] (both collected when present)
        Never follows robots-disallowed page= links; truncated listings
        are marked 'listing_truncated' and paginated exam pages are marked
        'completed_truncated' (page-1 questions only) for manual review.
        """
        from .metadata import MetadataExtractor
        extractor = self.extractor
        class_keys = source.params.get("class_keys", ["ssc", "dakhil", "hsc"])
        board_slugs = source.params.get("board_slugs") or list(sattacademy.BOARD_SLUGS)
        years = source.params.get("years") or list(range(2015, 2027))
        question_types = source.params.get("question_types", ["mcq", "written"])
        stats = {"listings": 0, "exams_found": 0, "exams_completed": 0,
                 "questions": 0, "failed": 0, "truncated": 0,
                 "questions_truncated": 0}

        self.db.upsert_source(source.name, source.base_url, source.enabled,
                              notes=source.notes)
        started = now_iso()
        done_exams = 0
        for class_key in class_keys:
            for board_slug in board_slugs:
                board = sattacademy.BOARD_SLUGS.get(board_slug, "unknown")
                for year in years:
                    url = sattacademy.listing_url(class_key, board_slug, year)
                    result = self.client.fetch(url)
                    stats["listings"] += 1
                    if result.blocked:
                        self.db.set_source_status(
                            source.name, "manual_review",
                            note=f"HTTP {result.status_code} at {url}")
                        stats["failed"] += 1
                        continue
                    if not result.ok:
                        stats["failed"] += 1
                        log.warning("Listing failed: %s (%s)", url, result.error)
                        continue
                    exams = sattacademy.parse_listing(result.text, url)
                    truncated = sattacademy.listing_is_truncated(result.text)
                    for exam in exams:
                        if limit is not None and done_exams >= limit:
                            break
                        exam_board = board
                        exam_subject = extractor.extract(
                            exam.get("exam_name", "")).get("subject")
                        exam_id = self.db.upsert_board_exam({
                            **exam,
                            "board": exam_board,
                            "class_key": class_key,
                            "subject": exam_subject,
                            "source_name": source.name,
                            "listing_url": url,
                            "scraped_at": now_iso(),
                            "status": "listing_truncated" if truncated else "listed",
                        })
                        stats["exams_found"] += 1
                        done_exams += 1
                        if truncated:
                            stats["truncated"] += 1
                            log.info("Truncated listing (page 2+ skipped per robots): %s", url)
                        got = self._collect_exam_questions(exam_id, exam, source,
                                                           question_types, extractor)
                        stats["questions"] += got["questions"]
                        stats["failed"] += got["failed"]
                        if got.get("truncated"):
                            stats["questions_truncated"] += 1
                        if got["completed"]:
                            stats["exams_completed"] += 1
                            if got.get("truncated"):
                                self.db.update_board_exam(
                                    exam_id, status="completed_truncated",
                                    missing_reason="questions_truncated: ?page= links present (robots-disallowed, page-1 only)")
                            else:
                                self.db.update_board_exam(exam_id, status="completed")
        self.db.log_run(f"scrape_board_exams:{source.name}", started, stats)
        return stats

    def _collect_exam_questions(self, exam_id, exam, source, question_types,
                                extractor) -> dict:
        """Fetch /mcq and /written pages for one exam; store questions.

        Only page-1 is fetched (robots disallows ?page=). When pagination
        links are detected the result carries truncated=True.
        """
        result_stats = {"questions": 0, "failed": 0, "completed": True,
                        "truncated": False}
        urls = {"mcq": exam.get("mcq_url"), "written": exam.get("written_url")}
        for qtype in question_types:
            page_url = urls.get(qtype)
            if not page_url:
                continue
            fetched = self.client.fetch(page_url)
            if fetched.blocked:
                self.db.set_source_status(
                    source.name, "manual_review",
                    note=f"HTTP {fetched.status_code} at {page_url}")
                self.db.update_board_exam(exam_id, status="failed",
                                          missing_reason=f"HTTP {fetched.status_code}")
                result_stats["failed"] += 1
                result_stats["completed"] = False
                continue
            if not fetched.ok:
                self.db.update_board_exam(exam_id, status="failed",
                                          missing_reason=fetched.error or "fetch failed")
                result_stats["failed"] += 1
                result_stats["completed"] = False
                continue
            questions = sattacademy.parse_exam_questions(
                fetched.text, page_url, qtype)
            if sattacademy.exam_has_more_pages(fetched.text):
                result_stats["truncated"] = True
                log.info("Truncated exam questions (page 2+ skipped per robots): %s",
                         page_url)
            for question in questions:
                self.db.upsert_exam_question({
                    **question,
                    "exam_id": exam_id,
                    "mcq_url": exam.get("mcq_url"),
                    "written_url": exam.get("written_url"),
                    "source_name": source.name,
                    "scraped_at": now_iso(),
                })
                result_stats["questions"] += 1
        return result_stats

    # ------------------------------------------------------------------ move
    def _relocate_if_needed(self, row: dict, record: PaperRecord) -> None:
        """Move a file from 'unknown/...' folders once metadata is complete."""
        old_path = row.get("file_path")
        if not old_path or "unknown" not in Path(old_path).parts:
            return
        desired = build_storage_path(
            self.settings.storage_root, record.board, record.year,
            record.subject, record.paper_type, record.source_name,
            record.file_name or Path(old_path).name,
        )
        if Path(old_path).resolve() == desired.resolve():
            return
        destination = unique_path(desired)
        try:
            shutil.move(old_path, str(destination))
        except OSError as exc:
            log.warning("Could not relocate %s: %s", old_path, exc)
            return
        record.file_path = str(destination)
        record.file_name = destination.name
        log.info("Relocated %s -> %s", old_path, destination)
