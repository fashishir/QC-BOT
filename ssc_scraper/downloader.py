"""File downloader: streaming, hashing, size caps, dedupe and storage layout.

Downloads via PoliteHttpClient (robots.txt gate + rate limiting + retries).
Files are streamed to a temporary location, hashed (SHA-256), checked for
duplicates, then moved into the clean folder structure:

    {storage_root}/{board}/{year}/{subject}/{paper_type}/{source_name}/{file_name}

Unknown facets go under 'unknown' and are relocated once metadata
enrichment (PDF text analysis) fills them in.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from urllib.parse import unquote, urlparse

from .config import Settings, SourceConfig
from .http_client import BlockedError, FetchError, PoliteHttpClient
from .logging_setup import get_logger
from .metadata import MetadataExtractor
from .models import PaperRecord
from .utils import (
    build_storage_path,
    guess_extension,
    now_iso,
    sanitize_filename,
    unique_path,
)

log = get_logger("downloader")


class Downloader:
    """Streams candidate documents to disk with hashing and deduplication."""

    def __init__(self, db, client: PoliteHttpClient, settings: Settings,
                 extractor: MetadataExtractor | None = None):
        self.db = db
        self.client = client
        self.settings = settings
        self.extractor = extractor or MetadataExtractor()
        self.max_bytes = settings.max_file_size_mb * 1024 * 1024

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _file_name_for(url: str, content_type: str | None) -> str:
        name = Path(unquote(urlparse(url).path)).name or "download"
        if not Path(name).suffix.lower():
            name += guess_extension(url, content_type)
        return sanitize_filename(name)

    def _record_failure(self, url: str, source: SourceConfig, reason: str) -> None:
        log.warning("Download failed: %s (%s)", url, reason)
        self.db.upsert_paper({
            "file_url": url,
            "source_name": source.name,
            "status": "failed",
            "missing_reason": reason[:500],
        })
        self.db.set_crawl_state(url, source.name, "failed", error=reason[:500])

    # ---------------------------------------------------------------- main
    def download_candidate(self, url: str, source: SourceConfig,
                           found_on: str | None = None,
                           context: str = "") -> PaperRecord | None:
        """Download one candidate document; returns the resulting PaperRecord."""
        existing = self.db.get_paper_by_url(url)
        if existing and existing["status"] not in ("failed",):
            # Resume support: this URL was already processed successfully.
            self.db.set_crawl_state(url, source.name, "processed")
            return PaperRecord.from_row(existing)

        try:
            response = self.client.fetch_stream(url)
        except BlockedError as exc:
            self.db.set_source_status(
                source.name, "manual_review",
                note=f"access-restricted download: {url}",
            )
            self._record_failure(url, source, str(exc))
            return None
        except FetchError as exc:
            self._record_failure(url, source, str(exc))
            return None

        if response.status_code >= 400:
            response.close()
            self._record_failure(url, source, f"HTTP {response.status_code}")
            return None

        file_name = self._file_name_for(url, response.headers.get("Content-Type"))
        tmp_dir = Path(self.settings.storage_root) / "_tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = tmp_dir / sanitize_filename(file_name)

        import hashlib
        digest = hashlib.sha256()
        size = 0
        try:
            with open(tmp_path, "wb") as handle:
                for chunk in response.iter_content(chunk_size=1 << 20):
                    if chunk:
                        size += len(chunk)
                        if size > self.max_bytes:
                            raise IOError(
                                f"file exceeds max_file_size_mb "
                                f"({self.settings.max_file_size_mb} MB) - aborted"
                            )
                        handle.write(chunk)
                        digest.update(chunk)
        except (IOError, OSError, Exception) as exc:  # size cap or network error
            response.close()
            tmp_path.unlink(missing_ok=True)
            self._record_failure(url, source, f"download error: {exc}")
            return None
        finally:
            response.close()

        file_hash = digest.hexdigest()

        # ---- duplicate detection (SHA-256 first) ----
        duplicate_of = self.db.get_paper_by_hash(
            file_hash, exclude_id=existing["id"] if existing else None
        )
        if duplicate_of:
            tmp_path.unlink(missing_ok=True)
            record = PaperRecord(
                file_url=url,
                source_page_url=found_on,
                source_name=source.name,
                status="duplicate",
                missing_reason=(
                    f"sha256 duplicate of paper #{duplicate_of['id']} "
                    f"({duplicate_of['file_url']})"
                ),
                file_hash=file_hash,
                file_size=size,
            )
            self.db.upsert_paper(record.to_dict())
            self.db.set_crawl_state(url, source.name, "processed")
            log.info("Duplicate skipped: %s (same content as #%s)", url, duplicate_of["id"])
            return record

        # ---- initial metadata + storage layout ----
        metadata = self.extractor.from_url_and_context(url, context)
        destination = build_storage_path(
            self.settings.storage_root,
            metadata.get("board"), metadata.get("year"),
            metadata.get("subject"), metadata.get("paper_type"),
            source.name, file_name,
        )
        destination = unique_path(destination)
        shutil.move(str(tmp_path), str(destination))

        record = PaperRecord(
            **metadata,
            file_url=url,
            source_page_url=found_on,
            source_name=source.name,
            downloaded_at=now_iso(),
            file_name=destination.name,
            file_path=str(destination),
            file_hash=file_hash,
            file_size=size,
            status="downloaded",
        )
        self.db.upsert_paper(record.to_dict())
        self.db.set_crawl_state(url, source.name, "processed")
        log.info("Downloaded: %s -> %s (%.1f KB)", url, destination, size / 1024)
        return record
