"""Tests for the Satt Academy board-exams adapter (offline, HTML fixtures)."""

from ssc_scraper import sattacademy


LISTING_HTML = """
<html><body>
<div class="loginAlertModal" data-total_question="25" data-id="9001"
     data-sub_cat="এসএসসি" data-year="2023"
     data-exam_name="রসায়ন"
     data-mcq-url="https://sattacademy.com/board-exams/chem-2023/mcq"
     data-written-url="https://sattacademy.com/board-exams/chem-2023/written">
  <span class="badge">MCQ 25</span>
  <span class="badge">CQ 40</span>
  <a href="https://sattacademy.com/board-exams/chem-2023/mcq"
     class="text-hover-primary text-black fs-4 mb-2">
     রসায়ন
  </a>
  <span>MCQ 25</span>
  <span>CQ 40</span>
</div>
</body></html>
"""

EXAM_HTML = """
<html><body>
<div>
  <span class="me-1 flex-shrink-0">1 . </span>
  <span class="question-span white-heading"><p>Fe<sup>3+</sup> sample?</p></span>
  <div class="toolbar-div">
    <div>
      <input class="form-check-input choosen-option" type="checkbox" value="1"
             name="option_266654" data-ques_id="266654" onclick="onlyOne(this)">
      <label>i ও ii</label>
    </div>
    <div>
      <input class="form-check-input choosen-option" type="checkbox" value="2"
             name="option_266655" data-ques_id="266654" onclick="onlyOne(this)">
      <label>শুধু iii</label>
    </div>
  </div>
</div>
</body></html>
"""

# New live card layout (Sep 2026): answer + data-id + images
MCQ_CARD_HTML = """
<html><body>
<div class="card card-bordered rounded-top-0 mb-5">
  <div class="card-header pt-2 mx-0 px-2 d-flex justify-content-between align-items-start">
    <div class="flex-grow-1"><div class="card-title">
      <a class="text-dark text-hover-primary fw-bolder w-100">
        <div class="p-0 m-0 fs-3 text-dark d-flex align-items-start">
          <div class="d-flex align-items-start flex-grow-1">
            <span class="me-1 flex-shrink-0">7 . </span>
            <span class="question-span white-heading">
              <figure class="image"><img src="https://sattacademy.com/uploads/ckeditor/1786189656.png"/></figure>
              <p>উদ্দীপক লোগোটি কোন আন্তর্জাতিক সংস্থার প্রতিনিধিত্ব করে?</p>
            </span>
          </div>
        </div>
      </a>
    </div></div>
  </div>
  <div class="card-body pb-3 pt-5 parent-card-body">
    <input name="active_mode" type="hidden" value="reading"/>
    <div class="reading-mode-data"><div class="row">
      <div class="col-md-6"><label for="kkradio_option1_671007"><p>রেড ক্রিসেন্ট</p></label></div>
      <div class="col-md-6"><label for="kkradio_option2_671007"><p>ইউনিসেফ</p></label></div>
      <div class="col-md-6"><label for="kkradio_option3_671007"><p>ওয়ার্ল্ড ভিশন</p></label></div>
      <div class="col-md-6"><label for="kkradio_option4_671007"><p>সেভ দ্য চিলড্রেন</p></label></div>
    </div></div>
    <div class="test-mode-data d-none"><div class="row parent-row">
      <input name="answer" type="hidden" value="4"/>
      <div class="click-option" data-id="671007" data-option_value="1"></div>
    </div></div>
  </div>
</div>
</body></html>
"""

WRITTEN_HTML = """
<html><body><ul>
<li>(১) <a href="https://sattacademy.com/question/korim-saheb-123">করিম সাহেব রাতের ট্রেনে ঢাকা যাবেন, দীর্ঘ উদ্দীপক পাঠ্য এখানে।</a> HSC | 0 | 27</li>
<li>(ক) <a href="https://sattacademy.com/question/khaddo-ki-24354">খাদ্য কী?</a> ১ Ans</li>
<li>(খ) <a href="https://sattacademy.com/question/unnoto-jati-456">উন্নত জাতি গঠনে শিক্ষার বিকল্প নেই-বুঝিয়ে লেখ।</a> ২ Ans</li>
</ul></body></html>
"""


def test_listing_url_never_contains_page_param():
    url = sattacademy.listing_url("ssc", "ঢাকা-বোর্ড", 2023)
    assert url.startswith("https://sattacademy.com/board-exams/")
    assert "page=" not in url
    assert "year=2023" in url


def test_hsc_listing_url_uses_verified_slug():
    url = sattacademy.listing_url("hsc", "সকল-বোর্ড", 2026)
    assert "page=" not in url
    assert "year=2026" in url
    # একাদশ-দ্বাদশ-শ্রেণি percent-encoded
    assert "%E0%A6%8F%E0%A6%95%E0%A6%BE%E0%A6%A6%E0%A6%B6" in url


def test_parse_listing_extracts_exam_card():
    exams = sattacademy.parse_listing(LISTING_HTML, "https://x/listing")
    assert len(exams) == 1
    exam = exams[0]
    assert exam["remote_id"] == "9001"
    assert exam["year"] == 2023
    assert exam["sub_cat"] == "এসএসসি"
    assert exam["mcq_url"].endswith("/mcq")
    assert exam["written_url"].endswith("/written")
    assert exam["mcq_count"] == 25
    assert exam["cq_count"] == 40


def test_listing_is_truncated_detects_page_links():
    assert sattacademy.listing_is_truncated(
        '<a href="/board-exams/x?board=y&year=2023&page=2">next</a>') is True
    assert sattacademy.listing_is_truncated(
        "<html><body><div class='loginAlertModal'></div></body></html>") is False


def test_exam_has_more_pages_detects_pagination():
    assert sattacademy.exam_has_more_pages(
        '<a href="/board-exams/x/mcq?page=2">2</a>') is True
    assert sattacademy.exam_has_more_pages("<html><body>no links</body></html>") is False


def test_parse_exam_questions_extracts_stem_options_and_ids():
    questions = sattacademy.parse_exam_questions(EXAM_HTML, "https://x/mcq", "mcq")
    assert len(questions) == 1
    question = questions[0]
    assert question["question_no"] == 1
    assert "Fe" in question["question_text"]
    assert question["remote_ques_id"] == "266654"
    # legacy fixture has no public answer
    assert question["answer"] is None
    option_texts = [o["text"] for o in question["options_json"]["options"]]
    assert len(option_texts) == 2


def test_parse_mcq_card_extracts_answer_images_and_id():
    questions = sattacademy.parse_exam_questions(MCQ_CARD_HTML, "https://x/mcq", "mcq")
    assert len(questions) == 1
    q = questions[0]
    assert q["remote_ques_id"] == "671007"
    assert q["answer"] == "4"
    assert "উদ্দীপক" in q["question_text"]
    assert q["options_json"]["images"] == [
        "https://sattacademy.com/uploads/ckeditor/1786189656.png"]
    assert len(q["options_json"]["options"]) == 4


def test_parse_written_extracts_stimulus_and_subquestions():
    questions = sattacademy.parse_exam_questions(WRITTEN_HTML, "https://x/written", "written")
    assert len(questions) == 3
    assert questions[0]["question_type"] == "written"
    assert "করিম" in questions[0]["question_text"]
    assert questions[1]["question_text"] == "খাদ্য কী?"
    assert questions[1]["remote_ques_id"] == "24354"
    assert questions[1]["options_json"]["marker"] == "ক"


def test_board_slug_map_covers_all_dropdown_boards():
    assert len(sattacademy.BOARD_SLUGS) == 13
    assert sattacademy.BOARD_SLUGS["যশোর-বোর্ড"] == "jessore"
    assert sattacademy.BOARD_SLUGS["দিনাজপুর-বোর্ড"] == "dinajpur"


def test_class_slugs_present():
    assert set(sattacademy.CLASS_SLUGS) == {"ssc", "dakhil", "hsc"}
