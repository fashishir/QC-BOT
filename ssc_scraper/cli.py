"""Command line interface for the SSC Archive Bot."""

from __future__ import annotations

import argparse
import json
import sys

from .config import load_config
from .db import Database
from .logging_setup import get_logger, setup_logging
from .pipeline import ScraperPipeline
from .reports import ReportGenerator

DEFAULT_CONFIG = "config/sources.example.yaml"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ssc-scraper",
        description=(
            "Ethical scraper archiving public Bangladesh SSC board question "
            "papers (2005-2026). Respects robots.txt and never bypasses "
            "authentication or protection systems."
        ),
    )
    parser.add_argument("--config", "-c", default=DEFAULT_CONFIG,
                        help=f"YAML config file (default: {DEFAULT_CONFIG})")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scrape = subparsers.add_parser(
        "scrape", help="crawl sources, download files and process them")
    scrape.add_argument("--source", help="limit the run to one source by name")
    scrape.add_argument("--limit", type=int,
                        help="max files to download this run (safety valve)")

    extract = subparsers.add_parser(
        "extract_text", help="extract PDF/DOCX text for downloaded papers")
    extract.add_argument("--force", action="store_true",
                         help="re-process papers already extracted")
    extract.add_argument("--limit", type=int, help="max papers this run")

    ocr = subparsers.add_parser(
        "ocr", help="OCR scanned papers (requires Tesseract + ben/eng packs)")
    ocr.add_argument("--limit", type=int, help="max papers this run")

    subparsers.add_parser("report", help="write the JSON/CSV dashboard")
    subparsers.add_parser("check_missing",
                          help="write the board-year-subject missing report")

    export = subparsers.add_parser("export_csv", help="export all papers to CSV")
    export.add_argument("--output", default="reports/papers_export.csv",
                        help="output CSV path")
    return parser


def _print_summary(summary: dict) -> None:
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    config = load_config(args.config)
    setup_logging(config.settings.logs_dir)
    log = get_logger("cli")
    db = Database(config.settings.database)

    try:
        if args.command == "scrape":
            pipeline = ScraperPipeline(config, db)
            try:
                summary = pipeline.scrape(source_name=args.source, limit=args.limit)
            finally:
                pipeline.close()
            _print_summary(summary)

        elif args.command == "extract_text":
            pipeline = ScraperPipeline(config, db)
            try:
                count = pipeline.extract_text(force=args.force, limit=args.limit)
            finally:
                pipeline.close()
            print(f"Extracted text for {count} paper(s)")

        elif args.command == "ocr":
            pipeline = ScraperPipeline(config, db)
            try:
                count = pipeline.run_ocr(limit=args.limit)
            finally:
                pipeline.close()
            print(f"OCR processed {count} paper(s)")

        elif args.command == "report":
            db.connect()
            db.create_schema()
            generator = ReportGenerator(db, config.settings)
            path = generator.write_dashboard()
            print(f"Dashboard written: {path}")

        elif args.command == "check_missing":
            db.connect()
            db.create_schema()
            generator = ReportGenerator(db, config.settings)
            path = generator.write_missing_report()
            print(f"Missing-data report written: {path}")

        elif args.command == "export_csv":
            db.connect()
            db.create_schema()
            generator = ReportGenerator(db, config.settings)
            path = generator.export_papers_csv(args.output)
            print(f"Papers exported: {path}")

    except FileNotFoundError as exc:
        log.error("%s", exc)
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover - defensive CLI guard
        log.exception("Unhandled error: %s", exc)
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
