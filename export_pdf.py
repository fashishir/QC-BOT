"""Export the 2025-2026 job-exam MCQ archive to PDF/CSV.

Examples:
  python export_pdf.py --year 2025 --with-answers
  python export_pdf.py --category "বিসিএস প্রিলিমিনারি" --with-answers
  python export_pdf.py --exam-id 12 --practice
  python export_pdf.py --csv questions.csv --with-answers
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

from job_scraper.config import ARCHIVE_DB
from job_scraper.export import export_csv, export_pdf_files, export_combined_pdf

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export job-exam MCQs")
    parser.add_argument("--db", default=ARCHIVE_DB)
    parser.add_argument("--exam-id", type=int)
    parser.add_argument("--category")
    parser.add_argument("--year", type=int, choices=(2025, 2026))
    parser.add_argument("--with-answers", action="store_true",
                        help="Include the answer key (default: questions only)")
    parser.add_argument("--practice", action="store_true",
                        help="Questions only, no answer key")
    parser.add_argument("--csv", metavar="PATH", help="Write a CSV instead of PDFs")
    parser.add_argument("--combined-pdf", metavar="PATH", nargs="?", const="pdf_exports/all_questions_with_answers.pdf",
                        help="Write a single combined PDF for all exams")
    parser.add_argument("--output-dir", default="pdf_exports")
    parser.add_argument("--limit", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not Path(args.db).exists():
        print(f"Archive not found: {args.db}", file=sys.stderr)
        return 1

    with_answers = args.with_answers and not args.practice
    if args.csv:
        count = export_csv(
            args.db, args.csv, exam_id=args.exam_id, category=args.category,
            year=args.year, limit=args.limit,
        )
        print(f"Wrote {count} questions to {args.csv}")
        return 0

    if args.combined_pdf:
        pdf_path = export_combined_pdf(
            args.db, args.combined_pdf, exam_id=args.exam_id, category=args.category,
            year=args.year, with_answers=with_answers, practice=args.practice,
            limit=args.limit,
        )
        print(f"Wrote combined PDF to {pdf_path}")
        return 0

    files = export_pdf_files(
        args.db, args.output_dir, exam_id=args.exam_id, category=args.category,
        year=args.year, with_answers=with_answers, practice=args.practice,
        limit=args.limit,
    )
    print(f"Wrote {len(files)} file(s) to {args.output_dir}")
    for path in files:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
