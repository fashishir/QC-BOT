"""Tests for metadata extraction (English + Bangla)."""

from ssc_scraper.metadata import MetadataExtractor, detect_language, extract_year


EXTRACTOR = MetadataExtractor()


def test_extract_year_range_filtering():
    assert extract_year("SSC exam 2023 question") == 2023
    assert extract_year("old papers 1999 and 2010") == 2010
    assert extract_year("nothing here 3000") is None


def test_from_filename_full_english():
    meta = EXTRACTOR.from_filename("SSC-2023-Dhaka-Board-Physics-MCQ-Question.pdf")
    assert meta["year"] == 2023
    assert meta["board"] == "dhaka"
    assert meta["subject"] == "physics"
    assert meta["paper_type"] == "mcq"
    assert meta["language"] == "english"


def test_from_filename_alias_spellings():
    meta = EXTRACTOR.from_filename("ssc_2015_comilla_board_higher_mathematics_creative.pdf")
    assert meta["board"] == "cumilla"
    assert meta["subject"] == "higher_mathematics"
    assert meta["paper_type"] == "creative"


def test_from_filename_bangla_word_file_name():
    meta = EXTRACTOR.from_filename("\u09ac\u09be\u0982\u09b2\u09be \u09e8\u09e6\u09e8\u09eb \u09aa\u09cd\u09b0\u09b6\u09cd\u09a8.pdf")
    assert meta["subject"] == "bangla"
    assert meta["year"] == 2025  # \u09e8\u09e6\u09e8\u09eb -> 2028? 2025 in Bangla digits


def test_bangla_digits_year_extraction():
    meta = EXTRACTOR.extract("\u09e8\u09e6\u09e8\u09e6 \u09b8\u09be\u09b2\u09c7\u09b0 \u098f\u09b8\u098f\u09b8\u09b8\u09bf \u09aa\u09b0\u09c0\u0995\u09cd\u09b7\u09be\u09b0 \u09aa\u09cd\u09b0\u09b6\u09cd\u09a8 \u0997\u09a3\u09bf\u09a4")
    assert meta["year"] == 2020
    assert meta["subject"] == "mathematics"
    assert meta["language"] == "bangla"


def test_set_code_and_shift_detection():
    meta = EXTRACTOR.extract("SSC 2022 Rajshahi Board Physics Set A morning")
    assert meta["set_code"] == "A"
    assert meta["shift"] == "morning"
    assert meta["board"] == "rajshahi"


def test_language_detection():
    assert detect_language("only english here") == "english"
    assert detect_language("\u09b6\u09c1\u09a7\u09c1 \u09ac\u09be\u0982\u09b2\u09be") == "bangla"
    assert detect_language("mixed \u09ac\u09be\u0982\u09b2\u09be english") == "mixed"
    assert detect_language("") is None


def test_board_madrasah_and_technical():
    assert EXTRACTOR.from_filename("dakhil_2019_madrasah_board_ict.pdf")["board"] == "madrasah"
    assert EXTRACTOR.from_filename("ssc_vocational_2021_chemistry.pdf")["board"] == "technical"


def test_bangladesh_not_matched_as_bangla_subject():
    meta = EXTRACTOR.from_filename("bangladesh-and-global-studies-2020-question.pdf")
    assert meta["subject"] == "general_knowledge"


def test_from_url_and_context():
    meta = EXTRACTOR.from_url_and_context(
        "https://example.gov.bd/files/2021/ssc-physics-question.pdf",
        "SSC 2021 Khulna Board",
    )
    assert meta["year"] == 2021
    assert meta["board"] == "khulna"
    assert meta["subject"] == "physics"
