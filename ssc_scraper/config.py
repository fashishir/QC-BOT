"""Configuration loading and validation (YAML driven)."""

from __future__ import annotations

from dataclasses import dataclass, field, fields as dc_fields
from pathlib import Path
from urllib.parse import urlparse

import yaml


@dataclass
class DatabaseConfig:
    backend: str = "sqlite"                 # 'sqlite' | 'postgres'
    sqlite_path: str = "ssc_archive.db"
    postgres_dsn: str | None = None         # postgresql://user:pass@host:5432/dbname


@dataclass
class OCRConfig:
    enabled: bool = False
    tesseract_cmd: str | None = None        # e.g. C:/Program Files/Tesseract-OCR/tesseract.exe
    languages: str = "ben+eng"              # Bangla + English
    min_text_chars_to_skip_ocr: int = 200   # PDFs with more text are not scanned
    max_pages: int = 30                     # OCR page cap per document


@dataclass
class SourceConfig:
    name: str
    base_url: str = ""
    seed_urls: list[str] = field(default_factory=list)
    allow_domains: list[str] = field(default_factory=list)
    enabled: bool = True
    keywords: list[str] = field(default_factory=list)   # URL filter hints
    notes: str | None = None                            # e.g. "manual review: ..."


@dataclass
class Settings:
    user_agent: str = (
        "SSC-Archive-Bot/1.0 (+educational archive; contact=please-set-email@example.com)"
    )
    request_delay_seconds: float = 3.0      # per-host politeness delay
    max_retries: int = 4
    backoff_factor: float = 2.0             # exponential backoff base
    request_timeout_seconds: int = 30
    respect_robots_txt: bool = True
    max_pages_per_source: int = 500
    max_file_size_mb: int = 100
    allowed_extensions: list[str] = field(
        default_factory=lambda: [".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png"]
    )
    download_html_pages: bool = False       # archive HTML pages as files too?
    storage_root: str = "data"
    logs_dir: str = "logs"
    reports_dir: str = "reports"
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    ocr: OCRConfig = field(default_factory=OCRConfig)


@dataclass
class AppConfig:
    settings: Settings
    sources: list[SourceConfig] = field(default_factory=list)

    def enabled_sources(self) -> list[SourceConfig]:
        return [s for s in self.sources if s.enabled]

    def get_source(self, name: str) -> SourceConfig | None:
        lowered = name.lower()
        return next((s for s in self.sources if s.name.lower() == lowered), None)


def _build(dc_cls, data: dict):
    """Instantiate dataclass *dc_cls* from a dict, ignoring unknown keys."""
    valid = {f.name for f in dc_fields(dc_cls)}
    return dc_cls(**{k: v for k, v in (data or {}).items() if k in valid})


def load_config(path: str | Path) -> AppConfig:
    """Load and validate a YAML config file."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8-sig")) or {}

    settings_raw = raw.get("settings") or {}
    settings = _build(Settings, settings_raw)
    settings.database = _build(DatabaseConfig, settings_raw.get("database") or {})
    settings.ocr = _build(OCRConfig, settings_raw.get("ocr") or {})

    if settings.request_delay_seconds < 1.0:
        raise ValueError(
            "settings.request_delay_seconds must be >= 1.0 (ethical scraping policy)"
        )
    if settings.max_retries < 1:
        settings.max_retries = 1

    sources: list[SourceConfig] = []
    for entry in raw.get("sources") or []:
        source = _build(SourceConfig, entry)
        if not source.name:
            raise ValueError("Every source needs a 'name' field")
        if not source.allow_domains and source.base_url:
            source.allow_domains = [urlparse(source.base_url).netloc]
        if not source.seed_urls and source.base_url:
            source.seed_urls = [source.base_url]
        sources.append(source)

    return AppConfig(settings=settings, sources=sources)
