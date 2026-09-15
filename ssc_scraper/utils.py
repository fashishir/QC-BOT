"""Utility helpers: hashing, filename sanitisation, storage paths, i18n digits."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

# Bangla numerals -> ASCII digits (year/code detection on Bangla pages)
BANGLA_DIGIT_TABLE = str.maketrans("\u09e6\u09e7\u09e8\u09e9\u09ea\u09eb\u09ec\u09ed\u09ee\u09ef", "0123456789")

# Characters that are invalid / risky in Windows + POSIX file names
_INVALID_FS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def now_iso() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def convert_bangla_digits(text: str) -> str:
    """Convert Bangla numerals (\u09e6-\u09ef) to ASCII digits."""
    return (text or "").translate(BANGLA_DIGIT_TABLE)


def sanitize_filename(name: str, max_len: int = 150) -> str:
    """Make an arbitrary string safe to use as a single file/folder name."""
    name = unicodedata.normalize("NFKC", str(name or ""))
    name = _INVALID_FS_CHARS.sub("_", name)
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"_+", "_", name)
    name = name.strip(" ._")
    name = name[:max_len]
    return name or "unnamed"


def sha256_of_file(path: str | Path, chunk_size: int = 1 << 20) -> str:
    """SHA-256 of a file on disk, streamed in chunks (memory-safe)."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_storage_path(
    root: str | Path,
    board: str | None,
    year: int | str | None,
    subject: str | None,
    paper_type: str | None,
    source_name: str | None,
    file_name: str,
) -> Path:
    """Build (and create) data/{board}/{year}/{subject}/{paper_type}/{source_name}/{file_name}.

    Unknown facets are stored under the literal folder 'unknown' and are
    relocated later once metadata enrichment fills them in.
    """

    def safe(value) -> str:
        return sanitize_filename(str(value or "unknown").strip().replace(" ", "_").lower() or "unknown")

    year_part = str(year).strip() if year not in (None, "") else "unknown"
    path = (
        Path(root)
        / safe(board)
        / year_part
        / safe(subject)
        / safe(paper_type)
        / safe(source_name)
        / sanitize_filename(file_name)
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def guess_extension(url: str, content_type: str | None = None) -> str:
    """Best-effort file extension from the URL path, then Content-Type."""
    suffix = Path(urlparse(url or "").path).suffix.lower()
    if suffix:
        return suffix
    content_type = (content_type or "").lower()
    mapping = {
        "application/pdf": ".pdf",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "text/html": ".html",
        "application/msword": ".doc",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    }
    for mime, ext in mapping.items():
        if mime in content_type:
            return ext
    return ".bin"


def normalized_text(text: str | None) -> str:
    """NFKC-normalise, lowercase and collapse whitespace/underscores/hyphens."""
    if not text:
        return ""
    value = unicodedata.normalize("NFKC", str(text)).lower().strip()
    return re.sub(r"[\s_\-]+", " ", value)


def unique_path(path: Path) -> Path:
    """Return a non-colliding variant of *path* by appending _1, _2, ..."""
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    for counter in range(1, 10_000):
        candidate = path.with_name(f"{stem}_{counter}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not find a free filename for {path}")
