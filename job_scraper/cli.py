"""Command-line entry point for the job-exam MCQ archive."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from .config import ARCHIVE_DB, load_config
from .db import Database, archive_summary, publish_archive
from .http_client import PoliteHttpClient
from .logging_setup import setup_logging
from .pipeline import import_livemcq, load_livemcq_config, scrape_sattacademy

DEFAULT_CONFIG = "config/job_sources.yaml"
DEFAULT_LIVEMCQ_CONFIG = "config/livemcq_pages.yaml"


def _client(config_path: str):
    config = load_config(config_path)
    setup_logging(config.settings.logs_dir)
    return config, PoliteHttpClient(config.settings)


def _open_raw(config) -> Database:
    return Database(config.settings.raw_db_path).initialize()


def cmd_scrape(args: argparse.Namespace) -> int:
    config, client = _client(args.config)
    with _open_raw(config) as db:
        result = scrape_sattacademy(
            db, client, config.settings,
            limit_categories=args.limit_categories,
            limit_exams=args.limit_exams,
            refresh=args.refresh,
        )
    print(f"SattAcademy: {result['exams_kept']} exams, "
          f"{result['questions']} questions, {result['answers']} answered, "
          f"{result['errors']} errors")
    return 0 if result["questions"] else 1


def cmd_import_livemcq(args: argparse.Namespace) -> int:
    config, client = _client(args.config)
    pages = load_livemcq_config(args.pages_config)
    with _open_raw(config) as db:
        result = import_livemcq(db, client, pages, refresh=args.refresh)
    print(f"Live MCQ: {result['imported']} pages, {result['questions']} questions, "
          f"{result['answers']} answered, {result['errors']} errors")
    return 0 if result["imported"] else 1


def cmd_publish(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    setup_logging(config.settings.logs_dir)
    stats = publish_archive(
        config.settings.raw_db_path,
        args.archive or ARCHIVE_DB,
        allow_empty=args.allow_empty,
    )
    print(f"Published {args.archive or ARCHIVE_DB}: "
          f"{stats['exams']} exams, {stats['questions']} questions, "
          f"{stats['answered']} answered")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    path = args.archive or ARCHIVE_DB
    if args.raw:
        path = config.settings.raw_db_path
    if not Path(path).exists():
        print(f"Database not found: {path}", file=sys.stderr)
        return 1
    summary = archive_summary(path)
    print(f"Database: {path}")
    print(f"Categories: {summary['categories']}")
    for key, value in summary["stats"].items():
        print(f"{key}: {value}")
    if summary["meta"]:
        print("Meta:")
        for key, value in sorted(summary["meta"].items()):
            print(f"  {key}: {value}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    path = args.archive or config.settings.raw_db_path
    if not Path(path).exists():
        print(f"Database not found: {path}", file=sys.stderr)
        return 1
    db = Database(path)
    rows = db.conn.execute(
        """
        SELECT e.exam_date, e.exam_name, e.total_questions,
               e.collected_questions, e.answered_questions,
               e.coverage_status, e.partial_reason, e.source_url,
               GROUP_CONCAT(c.name, '; ') AS categories
        FROM job_exams e
        LEFT JOIN job_exam_categories ec ON ec.exam_id = e.id
        LEFT JOIN job_categories c ON c.id = ec.category_id
        GROUP BY e.id
        ORDER BY e.exam_date DESC, e.exam_name
        """
    ).fetchall()
    out = Path(args.output or "reports/coverage.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "exam_date", "exam_name", "total_questions", "collected_questions",
            "answered_questions", "coverage_status", "partial_reason",
            "categories", "source_url",
        ])
        for row in rows:
            writer.writerow([row[col] for col in row.keys()])
    print(f"Wrote {len(rows)} exams to {out}")
    db.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="job_scraper",
        description="2025-2026 job-exam MCQ question bank",
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="YAML config path")
    sub = parser.add_subparsers(dest="command", required=True)

    scrape = sub.add_parser("scrape", help="Scrape SattAcademy job categories")
    scrape.add_argument("--limit-categories", type=int, default=None)
    scrape.add_argument("--limit-exams", type=int, default=None)
    scrape.add_argument("--refresh", action="store_true", help="Ignore HTML cache")
    scrape.set_defaults(func=cmd_scrape)

    lm = sub.add_parser("import-livemcq", help="Import approved Live MCQ pages")
    lm.add_argument("--pages-config", default=DEFAULT_LIVEMCQ_CONFIG)
    lm.add_argument("--refresh", action="store_true", help="Ignore HTML cache")
    lm.set_defaults(func=cmd_import_livemcq)

    publish = sub.add_parser("publish", help="Validate and build job_archive.db")
    publish.add_argument("--archive", default=None)
    publish.add_argument("--allow-empty", action="store_true")
    publish.add_argument("--allow-partial", action="store_true",
                         help="Accepted for compatibility; partial exams are always allowed")
    publish.set_defaults(func=cmd_publish)

    stats = sub.add_parser("stats", help="Show database counts")
    stats.add_argument("--archive", default=None)
    stats.add_argument("--raw", action="store_true")
    stats.set_defaults(func=cmd_stats)

    report = sub.add_parser("report", help="Write the exam coverage matrix")
    report.add_argument("--archive", default=None)
    report.add_argument("--output", default=None)
    report.set_defaults(func=cmd_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
