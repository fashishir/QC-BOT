"""Domain models shared by scrapers, importers, and storage."""

from __future__ import annotations

from dataclasses import dataclass, field

APPROVED_SOURCES = ("sattacademy", "livemcq", "jobsnoticebd", "official_pdf")
COVERAGE_STATES = ("full", "partial_pdf", "fallback_15", "missing")
ANSWER_STATUSES = ("published", "missing", "conflict")
REVIEW_STATUSES = ("auto", "needs_review", "approved", "rejected")
LICENSE_STATUSES = ("approved", "unknown", "rejected")


@dataclass
class CategoryRecord:
    slug: str
    name: str
    display_order: int = 0
    source_url: str | None = None


@dataclass
class ExamRecord:
    source: str
    source_id: str
    exam_name: str
    institution: str | None = None
    post_name: str | None = None
    exam_date: str | None = None
    year: int | None = None
    exam_type: str = "mcq"
    total_questions: int | None = None
    collected_questions: int = 0
    answered_questions: int = 0
    coverage_status: str = "fallback_15"
    is_partial: bool = True
    partial_reason: str | None = None
    source_url: str | None = None
    content_hash: str | None = None
    status: str = "published"


@dataclass
class QuestionRecord:
    question_no: int
    question_text: str
    options: list[str] = field(default_factory=list)
    answer_index: int | None = None
    answer_source: str = "sattacademy"
    answer_confidence: str = "high"
    review_status: str = "auto"
    images: list[str] = field(default_factory=list)
    source_url: str | None = None
    content_hash: str | None = None

    @property
    def answer_status(self) -> str:
        return "published" if self.answer_index in (1, 2, 3, 4) else "missing"
