"""Dashboards (JSON/CSV) and the missing board-year-subject report."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .logging_setup import get_logger
from .metadata import BOARDS, SUBJECTS
from .models import SUCCESS_STATUSES
from .utils import now_iso

log = get_logger("reports")

YEARS = list(range(2005, 2027))


class ReportGenerator:
    """Builds and writes the run dashboard and missing-combination report."""

    def __init__(self, db, settings):
        self.db = db
        self.settings = settings
        self.reports_dir = Path(settings.reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ data
    def build_dashboard(self) -> dict:
        counts = self.db.count_by_status()
        total_found = sum(counts.values())
        downloaded = sum(counts.get(status, 0) for status in SUCCESS_STATUSES)
        ocr_processed = counts.get("ocr_done", 0)

        combos = self.db.distinct_combos()
        boards_found = {c[0] for c in combos}
        years_found = {int(c[1]) for c in combos}
        subjects_found = {c[2] for c in combos}

        missing_years = [y for y in YEARS if y not in years_found]
        missing_boards = [b for b in BOARDS if b not in boards_found]
        missing_subjects = [s for s in SUBJECTS if s not in subjects_found]

        return {
            "generated_at": now_iso(),
            "totals": {
                "files_found": total_found,
                "files_downloaded": downloaded,
                "ocr_processed": ocr_processed,
                "duplicates": counts.get("duplicate", 0),
                "failed": counts.get("failed", 0),
                "ocr_pending": counts.get("ocr_pending", 0),
            },
            "status_breakdown": counts,
            "coverage": {
                "boards": sorted(boards_found),
                "years": sorted(years_found),
                "subjects": sorted(subjects_found),
                "per_board": self.db.count_by_field("board"),
                "per_year": self.db.count_by_field("year"),
                "per_subject": self.db.count_by_field("subject"),
                "per_source": self.db.count_by_field("source_name"),
            },
            "missing": {
                "years": missing_years,
                "boards": missing_boards,
                "subjects": missing_subjects,
                "missing_combination_count": len(self.missing_combinations()),
            },
        }

    def missing_combinations(self) -> list[dict]:
        """Board x year x subject triples with nothing successfully collected."""
        found = set(self.db.distinct_combos())
        missing = []
        for board in BOARDS:
            for year in YEARS:
                for subject in SUBJECTS:
                    if (board, year, subject) not in found:
                        missing.append({
                            "board": board,
                            "year": year,
                            "subject": subject,
                        })
        return missing

    # ----------------------------------------------------------------- write
    def write_dashboard(self) -> Path:
        dashboard = self.build_dashboard()
        json_path = self.reports_dir / "dashboard.json"
        json_path.write_text(
            json.dumps(dashboard, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        csv_path = self.reports_dir / "dashboard.csv"
        rows = ["section,key,value"]

        def flatten(prefix: str, data) -> None:
            if isinstance(data, dict):
                for key, value in data.items():
                    flatten(f"{prefix}.{key}" if prefix else str(key), value)
            elif isinstance(data, list):
                rows.append(f"{prefix},{' '.join(map(str, data))},")
            else:
                rows.append(f"{prefix},{data},")

        flatten("", dashboard)
        csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        log.info("Dashboard written: %s and %s", json_path, csv_path)
        return json_path

    def write_missing_report(self) -> Path:
        missing = self.missing_combinations()
        csv_path = self.reports_dir / "missing_combinations.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=["board", "year", "subject"]
            )
            writer.writeheader()
            writer.writerows(missing)
        json_path = self.reports_dir / "missing_combinations.json"
        json_path.write_text(
            json.dumps(missing, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log.info(
            "Missing-data report written: %d combinations -> %s",
            len(missing), csv_path,
        )
        return csv_path

    def export_board_exams(self, board: str | None = None,
                           year: int | None = None) -> list[Path]:
        """Export question-bank exams and questions grouped by board/exam.

        Writes reports/by_board_exam/{board}/{exam-slug}/questions.csv +
        exam.json for every matching exam, plus a coverage summary CSV.
        """
        from .utils import sanitize_filename

        exams = self.db.iter_board_exams(board=board, year=year)
        written: list[Path] = []
        coverage_rows: list[dict] = []
        for exam in exams:
            exam_dir = (self.reports_dir / "by_board_exam"
                        / sanitize_filename(exam.get("board") or "unknown")
                        / sanitize_filename(
                            f"{exam.get('year') or 'unknown'}_"
                            f"{(exam.get('subject') or 'unknown')}_exam{exam['id']}"))
            exam_dir.mkdir(parents=True, exist_ok=True)
            questions = self.db.iter_exam_questions(exam["id"])
            questions_path = exam_dir / "questions.csv"
            with open(questions_path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["question_no", "question_type", "question_text",
                                "options", "answer", "remote_ques_id",
                                "mcq_url", "written_url", "source_name",
                                "scraped_at"],
                    extrasaction="ignore",
                )
                writer.writeheader()
                for row in questions:
                    flat = dict(row)
                    flat["options"] = flat.pop("options_json", "")
                    writer.writerow(flat)
            meta = {k: exam.get(k) for k in (
                "id", "board", "class_key", "exam_name", "subject", "year",
                "total_questions", "mcq_count", "cq_count", "mcq_url",
                "written_url", "listing_url", "source_name", "scraped_at",
                "status", "missing_reason")}
            meta["questions_collected"] = len(questions)
            (exam_dir / "exam.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            coverage_rows.append({
                "board": exam.get("board"), "class": exam.get("class_key"),
                "year": exam.get("year"), "subject": exam.get("subject"),
                "exam_name": exam.get("exam_name"), "status": exam.get("status"),
                "questions_collected": len(questions),
                "mcq_url": exam.get("mcq_url"),
                "written_url": exam.get("written_url"),
            })
            written.append(questions_path)
        coverage_path = self.reports_dir / "board_exams_coverage.csv"
        with open(coverage_path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=[
                "board", "class", "year", "subject", "exam_name", "status",
                "questions_collected", "mcq_url", "written_url"])
            writer.writeheader()
            writer.writerows(coverage_rows)
        written.append(coverage_path)
        log.info("Exported %d board exam(s): %s", len(exams), coverage_path)
        return written

    def export_papers_csv(self, output_path: str | None = None) -> Path:
        """Export every paper row to CSV (default reports/papers_export.csv)."""
        destination = Path(output_path) if output_path else \
            self.reports_dir / "papers_export.csv"
        destination.parent.mkdir(parents=True, exist_ok=True)
        rows = self.db.iter_papers()
        fieldnames = [
            "id", "board", "year", "subject", "paper_type", "exam_code",
            "set_code", "shift", "language", "file_url", "source_page_url",
            "source_name", "downloaded_at", "file_name", "file_path",
            "file_hash", "file_size", "page_count", "ocr_confidence",
            "status", "missing_reason",
        ]
        with open(destination, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                row = dict(row)
                row.pop("ocr_text", None)  # keep the CSV readable
                writer.writerow(row)
        log.info("Exported %d paper rows -> %s", len(rows), destination)
        return destination
