"""Duplicate detection.

Two layers:
  1. Content identity  - SHA-256 file hash (strongest signal).
  2. Logical identity  - normalized (board, year, subject, paper_type)
     metadata signature; used when hashes differ but the same paper was
     collected twice under different encodings.
"""

from __future__ import annotations

from .logging_setup import get_logger
from .models import SUCCESS_STATUSES
from .utils import normalized_text

log = get_logger("dedupe")


def _get(record, key: str):
    """Read a field from either a dict row or a PaperRecord."""
    if isinstance(record, dict):
        return record.get(key)
    return getattr(record, key, None)


class DuplicateDetector:
    """Hash + metadata-signature duplicate checks backed by the DB."""

    def __init__(self, db):
        self.db = db

    @staticmethod
    def metadata_signature(record) -> str | None:
        """Normalized board|year|subject|paper_type signature, or None."""
        board = normalized_text(_get(record, "board"))
        year = _get(record, "year")
        subject = normalized_text(_get(record, "subject"))
        paper_type = normalized_text(_get(record, "paper_type")) or "unknown"
        if not board or not year or not subject:
            return None
        return f"{board}|{int(year)}|{subject}|{paper_type}"

    def signature_parts(self, record) -> dict:
        board = normalized_text(_get(record, "board"))
        year = _get(record, "year")
        subject = normalized_text(_get(record, "subject"))
        paper_type = normalized_text(_get(record, "paper_type")) or "unknown"
        return {"board": board, "year": int(year) if year else None,
                "subject": subject, "paper_type": paper_type}

    def check(self, file_hash: str | None, record=None,
              exclude_id: int | None = None) -> tuple[bool, str]:
        """Return (is_duplicate, reason) against already-stored papers."""
        if file_hash:
            existing = self.db.get_paper_by_hash(file_hash, exclude_id=exclude_id)
            if existing and existing.get("status") in SUCCESS_STATUSES:
                return True, f"sha256 match with paper #{existing['id']} ({existing['file_url']})"

        if record is not None:
            signature = self.metadata_signature(record)
            if signature:
                existing = self.db.get_paper_by_signature(
                    self.signature_parts(record), exclude_id=exclude_id
                )
                if existing:
                    return True, (
                        f"metadata signature match ({signature}) with paper "
                        f"#{existing['id']} ({existing['file_url']})"
                    )
        return False, ""
