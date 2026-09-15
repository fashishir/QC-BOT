"""Tests for YAML config loading and validation."""

import textwrap

import pytest

from ssc_scraper.config import load_config


CONFIG = textwrap.dedent("""
    settings:
      user_agent: "TestBot/0.1 (+contact=tests@example.com)"
      request_delay_seconds: 2.0
      database:
        backend: sqlite
        sqlite_path: test_cfg.db
      ocr:
        enabled: false
        languages: ben+eng
    sources:
      - name: src_one
        base_url: https://one.example.org
        seed_urls:
          - https://one.example.org/archives
        keywords: [ssc]
      - name: src_two
        base_url: https://two.example.org
        enabled: false
        notes: "manual review: robots.txt disallows /archives"
    """)


def test_load_config_defaults_and_derived_fields(tmp_path):
    config_file = tmp_path / "cfg.yaml"
    config_file.write_text(CONFIG, encoding="utf-8")
    app = load_config(config_file)

    assert app.settings.user_agent.startswith("TestBot")
    assert app.settings.request_delay_seconds == 2.0
    assert app.settings.database.sqlite_path == "test_cfg.db"
    assert app.settings.ocr.languages == "ben+eng"

    # allow_domains and seed_urls fall back to base_url when omitted
    first = app.sources[0]
    assert first.allow_domains == ["one.example.org"]
    assert first.seed_urls == ["https://one.example.org/archives"]


def test_enabled_sources_filtering(tmp_path):
    config_file = tmp_path / "cfg.yaml"
    config_file.write_text(CONFIG, encoding="utf-8")
    app = load_config(config_file)
    assert [s.name for s in app.enabled_sources()] == ["src_one"]
    assert app.get_source("SRC_TWO").enabled is False
    assert app.get_source("nope") is None


def test_unethical_delay_is_rejected(tmp_path):
    config_file = tmp_path / "cfg.yaml"
    config_file.write_text(
        "settings:\n  request_delay_seconds: 0.1\n", encoding="utf-8"
    )
    with pytest.raises(ValueError):
        load_config(config_file)


def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_config("definitely/missing/config.yaml")


def test_example_config_loads():
    """The shipped example config must always stay valid."""
    from pathlib import Path

    example = Path(__file__).resolve().parent.parent / "config" / "sources.example.yaml"
    app = load_config(example)
    assert app.sources, "example config should contain source entries"
    assert all(s.enabled is False for s in app.sources), \
        "ethical default: every example source must ship disabled"
