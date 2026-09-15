"""Tests for utility helpers."""

from pathlib import Path

from ssc_scraper.utils import (
    build_storage_path,
    convert_bangla_digits,
    guess_extension,
    normalized_text,
    sanitize_filename,
    sha256_of_bytes,
    unique_path,
)


def test_bangla_digits_conversion():
    assert convert_bangla_digits("\u09e8\u09e6\u09e8\u09e6") == "2020"
    assert convert_bangla_digits("SSC \u09e8\u09e6\u09e8\u09ef") == "SSC 2029"


def test_sanitize_filename_removes_invalid_characters():
    assert sanitize_filename('bad:name<>"/\\|?*') == "bad_name"
    assert sanitize_filename("   ") == "unnamed"
    assert sanitize_filename("SSC 2023 Question.pdf") == "SSC_2023_Question.pdf"


def test_sha256_of_bytes_known_vector():
    assert sha256_of_bytes(b"hello") == (
        "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    )


def test_build_storage_path_layout(tmp_path: Path):
    path = build_storage_path(tmp_path, "Dhaka Board", 2023, "Physics",
                              "MCQ", "src", "q.pdf")
    expected = tmp_path / "dhaka_board" / "2023" / "physics" / "mcq" / "src" / "q.pdf"
    assert path == expected
    assert path.parent.exists()


def test_build_storage_path_unknown_facets(tmp_path: Path):
    path = build_storage_path(tmp_path, None, None, "", None, None, "q.pdf")
    assert path == tmp_path / "unknown" / "unknown" / "unknown" / "unknown" / "unknown" / "q.pdf"


def test_guess_extension():
    assert guess_extension("https://x.y/a/b/file.pdf") == ".pdf"
    assert guess_extension("https://x.y/file", "application/pdf") == ".pdf"
    assert guess_extension("https://x.y/file", "image/png") == ".png"


def test_normalized_text():
    assert normalized_text("  Higher-Mathematics_2023 ") == "higher mathematics 2023"
    assert normalized_text(None) == ""


def test_unique_path(tmp_path: Path):
    first = tmp_path / "a.pdf"
    first.write_text("x")
    second = unique_path(first)
    assert second.name == "a_1.pdf"
    assert unique_path(tmp_path / "missing.pdf") == tmp_path / "missing.pdf"
