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
