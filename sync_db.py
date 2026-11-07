"""Validate the raw scrape and publish the app-facing archive.

Usage:
  python sync_db.py
  python sync_db.py --allow-empty
"""

from __future__ import annotations

import argparse
import io
import sys

from job_scraper.config import ARCHIVE_DB, load_config
from job_scraper.db import publish_archive
from job_scraper.logging_setup import setup_logging

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish job_archive.db")
    parser.add_argument("--config", default="config/job_sources.yaml")
    parser.add_argument("--archive", default=ARCHIVE_DB)
    parser.add_argument("--allow-empty", action="store_true")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    setup_logging(config.settings.logs_dir)
    stats = publish_archive(
        config.settings.raw_db_path, args.archive, allow_empty=args.allow_empty,
    )
    print(f"Published {args.archive}")
    print(f"  exams:    {stats['exams']}")
    print(f"  questions:{stats['questions']}")
    print(f"  answered: {stats['answered']}")
    print(f"  missing:  {stats['missing']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
