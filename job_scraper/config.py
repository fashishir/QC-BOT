"""Configuration loading and validation (YAML driven)."""

from __future__ import annotations

from dataclasses import dataclass, field, fields as dc_fields
from pathlib import Path

import yaml

RAW_DB = "job_questions.db"
ARCHIVE_DB = "job_archive.db"


@dataclass
class DatabaseConfig:
    backend: str = "sqlite"                 # 'sqlite' | 'postgres'
    sqlite_path: str = RAW_DB
    postgres_dsn: str | None = None


@dataclass
class Settings:
    user_agent: str = (
        "JobQuestionBank/1.0 (+educational archive; contact=local-project)"
    )
    request_delay_seconds: float = 2.0
    max_retries: int = 3
    backoff_factor: float = 2.0
    request_timeout_seconds: int = 45
    respect_robots_txt: bool = True
    storage_root: str = "data"
    logs_dir: str = "logs"
    reports_dir: str = "reports"
    database: DatabaseConfig = field(default_factory=DatabaseConfig)

    @property
    def raw_db_path(self) -> str:
        return self.database.sqlite_path or RAW_DB


@dataclass
class SourceConfig:
    name: str
    base_url: str = ""
    enabled: bool = True
    license_status: str = "unknown"
    permission_note: str | None = None
    publish_allowed: bool = False
    params: dict = field(default_factory=dict)


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
        sources.append(source)

    return AppConfig(settings=settings, sources=sources)
