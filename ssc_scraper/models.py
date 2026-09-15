"""Data model for a collected question paper. Mirrors the DB 'papers' schema."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Optional

# Lifecycle states a paper record moves through (checkpoint/resume machine).
STATUSES = (
    "discovered",     # URL found, not yet downloaded
    "downloaded",     # file on disk
    "extracted",      # PDF text extracted + metadata enriched
    "ocr_done",       # OCR performed (scanned PDF)
    "ocr_pending",    # OCR needed but Tesseract unavailable -> manual review
    "duplicate",      # SHA-256 / metadata duplicate of another record
    "failed",         # download or processing failure (see missing_reason)
    "skipped",        # intentionally skipped (robots, size cap, disabled)
)

# Statuses that count as "we have this paper" for coverage reporting.
SUCCESS_STATUSES = ("downloaded", "extracted", "ocr_done")


@dataclass
class PaperRecord:
    """Normalized metadata for one question-paper file."""

    board: Optional[str] = None
    year: Optional[int] = None
    subject: Optional[str] = None
    paper_type: Optional[str] = None
    exam_code: Optional[str] = None
    set_code: Optional[str] = None
    shift: Optional[str] = None
    language: Optional[str] = None
    file_url: str = ""
    source_page_url: Optional[str] = None
    source_name: Optional[str] = None
    downloaded_at: Optional[str] = None
    file_name: Optional[str] = None
    file_path: Optional[str] = None
    file_hash: Optional[str] = None
    file_size: Optional[int] = None
    page_count: Optional[int] = None
    ocr_text: Optional[str] = None
    ocr_confidence: Optional[float] = None
    status: str = "discovered"
    missing_reason: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Return all fields as a plain dict (DB row shape)."""
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "PaperRecord":
        """Build a record from a DB row dict, ignoring unknown keys."""
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in dict(row).items() if k in known})

    def merge_metadata(self, candidate: dict[str, Any]) -> bool:
        """Fill in empty fields from *candidate*; never overwrite known values.

        Returns True if anything changed.
        """
        changed = False
        for key, value in candidate.items():
            if key not in {f.name for f in fields(self)}:
                continue
            if value in (None, "", "unknown"):
                continue
            current = getattr(self, key)
            if current in (None, "", "unknown"):
                setattr(self, key, value)
                changed = True
        return changed
