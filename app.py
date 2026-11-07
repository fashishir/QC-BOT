"""চাকরি পরীক্ষার MCQ প্রশ্নব্যাংক (২০২৫–২০২৬).

Reads only ``job_archive.db`` (the validated, published archive). There is no
fallback to raw scrape data or to any old SSC/HSC database.
"""

from __future__ import annotations

import html
import json
import sqlite3
from pathlib import Path

import streamlit as st

from job_scraper.config import ARCHIVE_DB

st.set_page_config(
    page_title="চাকরি পরীক্ষার MCQ প্রশ্নব্যাংক (২০২৫–২০২৬)",
    page_icon="📚",
    layout="wide",
)

DB_PATH = Path(ARCHIVE_DB)

COVERAGE_LABELS = {
    "full": "পূর্ণ",
    "partial_pdf": "আংশিক",
    "fallback_15": "ফলব্যাক ১৫",
    "missing": "অনুপলব্ধ",
}
COVERAGE_CLASSES = {
    "full": "badge-full",
    "partial_pdf": "badge-partial",
    "fallback_15": "badge-fallback",
    "missing": "badge-missing",
}
SOURCE_CLASSES = {
    "Live MCQ": "badge-live",
    "JobsNoticeBD": "badge-jobs",
    "SattAcademy": "badge-satta",
    "Official PDF": "badge-official",
}


# --------------------------------------------------------------------- styling
def inject_css() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Bengali:wght@400;500;600;700&display=swap');
        html, body, [class*="css"] { font-family: 'Noto Sans Bengali', 'Nirmala UI', sans-serif; }
        .block-container { padding-top: 1.6rem; max-width: 1240px; }
        h1, h2, h3 { color: #0b3b6f; letter-spacing: 0; }
        .hero { background: linear-gradient(135deg, #0b3b6f 0%, #0b6bcb 100%);
                color: #fff; border-radius: 14px; padding: 22px 26px; margin-bottom: 18px; }
        .hero h1 { color: #fff; margin: 0 0 6px; font-size: 1.75rem; }
        .hero p { margin: 0; opacity: .92; font-size: .98rem; }
        .stat-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin-bottom: 14px; }
        .stat-card { background: #fff; border: 1px solid #e5e9f0; border-radius: 10px;
                     padding: 12px 14px; box-shadow: 0 1px 3px rgba(16,24,40,.04); }
        .stat-card .num { font-size: 1.42rem; font-weight: 700; color: #0b3b6f; line-height: 1.2; }
        .stat-card .lbl { font-size: .78rem; color: #64748b; margin-top: 2px; }
        .exam-card { background: #fff; border: 1px solid #e5e9f0; border-radius: 12px;
                     padding: 14px 16px; margin-bottom: 10px; box-shadow: 0 1px 3px rgba(16,24,40,.04); }
        .exam-title { font-weight: 600; font-size: 1.02rem; color: #172033; margin-bottom: 4px; }
        .exam-meta { font-size: .82rem; color: #64748b; margin-bottom: 8px; }
        .badge { display: inline-block; padding: 2px 9px; border-radius: 999px;
                 font-size: .74rem; font-weight: 600; margin-right: 5px; }
        .badge-full { background: #dcfce7; color: #166534; }
        .badge-partial { background: #fef3c7; color: #92400e; }
        .badge-fallback { background: #e0e7ff; color: #3730a3; }
        .badge-missing { background: #f3f4f6; color: #4b5563; }
        .badge-live { background: #dbeafe; color: #1e40af; }
        .badge-jobs { background: #fce7f3; color: #9d174d; }
        .badge-satta { background: #ede9fe; color: #5b21b6; }
        .badge-official { background: #cffafe; color: #155e75; }
        .q-card { background: #fff; border: 1px solid #e5e9f0; border-radius: 10px;
                  padding: 14px 16px; margin-bottom: 12px; }
        .q-stem { font-weight: 500; margin-bottom: 8px; line-height: 1.7; }
        .q-no { color: #0b6bcb; font-weight: 700; margin-right: 4px; }
        .opt { padding: 3px 0; color: #334155; }
        .opt-correct { color: #166534; font-weight: 700; }
        .ans-pill { display: inline-block; margin-top: 6px; padding: 2px 10px;
                    background: #dcfce7; color: #166534; border-radius: 999px;
                    font-size: .8rem; font-weight: 600; }
        .ans-missing { display: inline-block; margin-top: 6px; padding: 2px 10px;
                       background: #f3f4f6; color: #6b7280; border-radius: 999px;
                       font-size: .8rem; font-weight: 600; }
        .expl-box { background: #f0fdf4; border-left: 3px solid #16a34a; padding: 8px 12px;
                    border-radius: 4px; font-size: .86rem; color: #1e293b; margin-top: 8px; line-height: 1.55; }
        .notice { background: #fff7e6; border-left: 4px solid #d97706; padding: 8px 12px;
                  border-radius: 4px; font-size: .86rem; color: #92400e; margin-bottom: 12px; }
        .source-note { background: #eef6ff; border-left: 4px solid #0b6bcb; padding: 10px 14px;
                       border-radius: 4px; font-size: .88rem; color: #1e3a5f; }
        div[data-testid="stSidebar"] { background: #f8fafc; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ------------------------------------------------------------------------ data
def db_available() -> bool:
    return DB_PATH.exists()


def connect() -> sqlite3.Connection:
    p = DB_PATH.resolve().as_posix()
    try:
        conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("SELECT 1")
        return conn
    except sqlite3.OperationalError:
        conn = sqlite3.connect(f"file:{p}?immutable=1", uri=True)
        conn.row_factory = sqlite3.Row
        return conn


@st.cache_data(ttl=60, show_spinner=False)
def load_summary() -> dict:
    conn = connect()
    one = lambda sql: int(conn.execute(sql).fetchone()[0] or 0)  # noqa: E731
    meta = {row["key"]: row["value"] for row in conn.execute("SELECT * FROM archive_meta")}
    result = {
        "categories": one("SELECT COUNT(*) FROM job_categories"),
        "exams": one("SELECT COUNT(*) FROM job_exams"),
        "questions": one("SELECT COUNT(*) FROM job_questions"),
        "answered": one("SELECT COUNT(*) FROM job_questions WHERE answer_status='published'"),
        "full": one("SELECT COUNT(*) FROM job_exams WHERE coverage_status='full'"),
        "partial": one("SELECT COUNT(*) FROM job_exams WHERE coverage_status<>'full'"),
        "last_update": meta.get("built_at", "—"),
    }
    conn.close()
    return result


@st.cache_data(ttl=60, show_spinner=False)
def load_categories() -> list[dict]:
    conn = connect()
    rows = [dict(r) for r in conn.execute(
        """
        SELECT c.*, COUNT(DISTINCT ec.exam_id) AS exam_count
        FROM job_categories c
        LEFT JOIN job_exam_categories ec ON ec.category_id = c.id
        GROUP BY c.id ORDER BY c.display_order, c.name
        """
    )]
    conn.close()
    return rows


@st.cache_data(ttl=60, show_spinner=False)
def load_institutions() -> list[str]:
    conn = connect()
    rows = [r["institution"] for r in conn.execute(
        "SELECT DISTINCT institution FROM job_exams WHERE institution IS NOT NULL "
        "AND institution <> '' ORDER BY institution"
    )]
    conn.close()
    return rows


@st.cache_data(ttl=60, show_spinner=False)
def load_exams(category_names: tuple[str, ...], institution: str | None,
               year: int | None, coverage: str | None, answer_filter: str | None,
               search: str) -> list[dict]:
    conn = connect()
    clauses = ["1=1"]
    params: list = []
    if category_names:
        placeholders = ",".join("?" for _ in category_names)
        clauses.append(
            f"e.id IN (SELECT ec.exam_id FROM job_exam_categories ec "
            f"JOIN job_categories c ON c.id=ec.category_id WHERE c.name IN ({placeholders}))"
        )
        params.extend(category_names)
    if institution:
        clauses.append("e.institution = ?")
        params.append(institution)
    if year:
        clauses.append("e.year = ?")
        params.append(year)
    if coverage == "full":
        clauses.append("e.coverage_status = 'full'")
    elif coverage == "partial":
        clauses.append("e.coverage_status IN ('partial_pdf','fallback_15')")
    if answer_filter == "with":
        clauses.append("e.answered_questions > 0")
    elif answer_filter == "missing":
        clauses.append("e.answered_questions < e.collected_questions")
    if search:
        clauses.append(
            "(e.exam_name LIKE ? OR EXISTS (SELECT 1 FROM job_questions q "
            "WHERE q.exam_id=e.id AND q.question_text LIKE ?))"
        )
        like = f"%{search}%"
        params.extend([like, like])
    sql = f"""
        SELECT e.*, GROUP_CONCAT(DISTINCT c.name) AS category_names,
               (SELECT d.source_name FROM job_documents d
                WHERE d.exam_id=e.id AND d.publish_allowed=1
                ORDER BY CASE d.source_name WHEN 'Live MCQ' THEN 0 ELSE 1 END LIMIT 1)
               AS content_source
        FROM job_exams e
        LEFT JOIN job_exam_categories ec ON ec.exam_id=e.id
        LEFT JOIN job_categories c ON c.id=ec.category_id
        WHERE {' AND '.join(clauses)}
        GROUP BY e.id
        ORDER BY e.exam_date DESC, e.exam_name
    """
    rows = [dict(r) for r in conn.execute(sql, params)]
    conn.close()
    return rows


@st.cache_data(ttl=60, show_spinner=False)
def load_exam(exam_id: int) -> dict | None:
    conn = connect()
    row = conn.execute(
        """
        SELECT e.*, GROUP_CONCAT(DISTINCT c.name) AS category_names,
               (SELECT d.source_name FROM job_documents d
                WHERE d.exam_id=e.id AND d.publish_allowed=1
                ORDER BY CASE d.source_name WHEN 'Live MCQ' THEN 0 ELSE 1 END LIMIT 1)
               AS content_source
        FROM job_exams e
        LEFT JOIN job_exam_categories ec ON ec.exam_id=e.id
        LEFT JOIN job_categories c ON c.id=ec.category_id
        WHERE e.id=? GROUP BY e.id
        """,
        (exam_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


@st.cache_data(ttl=60, show_spinner=False)
def load_questions(exam_id: int) -> list[dict]:
    conn = connect()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM job_questions WHERE exam_id=? ORDER BY question_no", (exam_id,)
    )]
    conn.close()
    return rows


@st.cache_data(ttl=60, show_spinner=False)
def search_questions(term: str, category_names: tuple[str, ...], year: int | None,
                     limit: int = 100) -> list[dict]:
    conn = connect()
    clauses = ["q.question_text LIKE ?"]
    params: list = [f"%{term}%"]
    if category_names:
        placeholders = ",".join("?" for _ in category_names)
        clauses.append(
            f"e.id IN (SELECT ec.exam_id FROM job_exam_categories ec "
            f"JOIN job_categories c ON c.id=ec.category_id WHERE c.name IN ({placeholders}))"
        )
        params.extend(category_names)
    if year:
        clauses.append("e.year = ?")
        params.append(year)
    params.append(limit)
    rows = [dict(r) for r in conn.execute(
        f"""
        SELECT q.*, e.exam_name, e.exam_date, e.year, e.coverage_status
        FROM job_questions q JOIN job_exams e ON e.id=q.exam_id
        WHERE {' AND '.join(clauses)}
        ORDER BY e.exam_date DESC, q.question_no LIMIT ?
        """,
        params,
    )]
    conn.close()
    return rows


@st.cache_data(ttl=60, show_spinner=False)
def load_coverage() -> list[dict]:
    conn = connect()
    rows = [dict(r) for r in conn.execute(
        """
        SELECT c.name AS category, c.display_order,
               COUNT(DISTINCT e.id) AS exams,
               COUNT(q.id) AS questions,
               SUM(CASE WHEN q.answer_status='published' THEN 1 ELSE 0 END) AS answered
        FROM job_categories c
        LEFT JOIN job_exam_categories ec ON ec.category_id=c.id
        LEFT JOIN job_exams e ON e.id=ec.exam_id
        LEFT JOIN job_questions q ON q.exam_id=e.id
        GROUP BY c.id ORDER BY c.display_order, c.name
        """
    )]
    conn.close()
    return rows


# ------------------------------------------------------------------ components
def badge(text: str, css_class: str) -> str:
    return f"<span class='badge {css_class}'>{html.escape(text)}</span>"


def source_badge(source: str | None) -> str:
    name = source or "SattAcademy"
    return badge(name, SOURCE_CLASSES.get(name, "badge-satta"))


def coverage_badge(status: str) -> str:
    return badge(COVERAGE_LABELS.get(status, status), COVERAGE_CLASSES.get(status, "badge-missing"))


def render_header(summary: dict) -> None:
    answered_pct = (summary["answered"] / summary["questions"] * 100) if summary["questions"] else 0
    st.markdown(
        f"""
        <div class="hero">
          <h1>চাকরি পরীক্ষার MCQ প্রশ্নব্যাংক (২০২৫–২০২৬)</h1>
          <p>বিসিএস, এনটিআরসিএ, বিচার বিভাগ, ব্যাংক, মন্ত্রণালয়, বাহিনী ও অন্যান্য সরকারি-বেসরকারি চাকরি পরীক্ষার উত্তরসহ বহুনির্বাচনি প্রশ্ন।</p>
        </div>
        <div class="stat-row">
          <div class="stat-card"><div class="num">{summary['exams']}</div><div class="lbl">পরীক্ষা</div></div>
          <div class="stat-card"><div class="num">{summary['questions']:,}</div><div class="lbl">মোট MCQ</div></div>
          <div class="stat-card"><div class="num">{summary['answered']:,}</div><div class="lbl">উত্তরসহ MCQ ({answered_pct:.0f}%)</div></div>
          <div class="stat-card"><div class="num">{summary['full']}</div><div class="lbl">পূর্ণ সেট</div></div>
          <div class="stat-card"><div class="num">{summary['partial']}</div><div class="lbl">আংশিক সেট</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_exam_card(exam: dict) -> None:
    source = source_badge(exam.get("content_source"))
    coverage = coverage_badge(exam["coverage_status"])
    categories = html.escape(exam.get("category_names") or "—")
    collected = exam.get("collected_questions") or 0
    expected = exam.get("total_questions") or collected
    st.markdown(
        f"""
        <div class="exam-card">
          <div class="exam-title">{html.escape(exam['exam_name'])}</div>
          <div class="exam-meta">{html.escape(str(exam.get('exam_date') or 'তারিখ নেই'))} · {categories}
            · প্রশ্ন {collected}/{expected} · উত্তর {exam.get('answered_questions') or 0}</div>
          <div>{coverage}{source}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_question(q: dict, show_answer: bool) -> None:
    options = [q.get(f"option_{i}") or "" for i in range(1, 5)]
    symbols = ["(ক)", "(খ)", "(গ)", "(ঘ)"]
    answer = q.get("answer_index")
    rows = []
    for idx, text in enumerate(options, start=1):
        css = "opt-correct" if show_answer and answer == idx else "opt"
        mark = " ✔" if show_answer and answer == idx else ""
        rows.append(f"<div class='{css}'>{symbols[idx-1]} {html.escape(text)}{mark}</div>")
    if q.get("answer_status") == "published":
        footer = f"<div class='ans-pill'>সঠিক উত্তর: {symbols[answer-1]}</div>" if show_answer else ""
    else:
        footer = "<div class='ans-missing'>উত্তর প্রকাশিত হয়নি</div>"

    expl_div = ""
    if show_answer and q.get("explanation"):
        formatted_expl = html.escape(str(q["explanation"])).replace("\n", "<br>")
        expl_div = f"<div class='expl-box'><b>ব্যাখ্যা:</b><br>{formatted_expl}</div>"

    st.markdown(
        f"<div class='q-card'><div class='q-stem'><span class='q-no'>{q['question_no']}.</span>"
        f"{html.escape(q['question_text'])}</div>{''.join(rows)}{footer}{expl_div}</div>",
        unsafe_allow_html=True,
    )


# ----------------------------------------------------------------------- views
def render_library(summary: dict, categories: list[dict], institutions: list[str]) -> None:
    st.sidebar.header("ফিল্টার")
    category_names = tuple(c["name"] for c in categories)
    selected_categories = st.sidebar.multiselect("বিভাগ", category_names)
    year_label = st.sidebar.selectbox("বছর", ["সব", "২০২৬", "২০২৫"])
    year = {"সব": None, "২০২৬": 2026, "২০২৫": 2025}[year_label]
    institution = st.sidebar.selectbox("প্রতিষ্ঠান", ["সব"] + institutions)
    institution = None if institution == "সব" else institution
    coverage_label = st.sidebar.selectbox("কভারেজ", ["সব", "পূর্ণ সেট", "আংশিক সেট"])
    coverage = {"সব": None, "পূর্ণ সেট": "full", "আংশিক সেট": "partial"}[coverage_label]
    answer_label = st.sidebar.selectbox("উত্তর", ["সব", "উত্তরসহ", "উত্তর অনুপস্থিত"])
    answer_filter = {"সব": None, "উত্তরসহ": "with", "উত্তর অনুপস্থিত": "missing"}[answer_label]
    search = st.sidebar.text_input("পরীক্ষা/প্রশ্ন খুঁজুন", "")

    if st.sidebar.button("ফিল্টার মুছুন", use_container_width=True):
        st.session_state.pop("selected_exam_id", None)
        st.cache_data.clear()
        st.rerun()

    exams = load_exams(
        tuple(selected_categories), institution, year, coverage, answer_filter, search.strip(),
    )
    st.caption(f"{len(exams)}টি পরীক্ষা পাওয়া গেছে")

    left, right = st.columns([1.05, 1.95], gap="large")
    with left:
        st.subheader("পরীক্ষার তালিকা")
        if not exams:
            st.info("এই ফিল্টারে কোনো পরীক্ষা নেই।")
        for exam in exams[:80]:
            render_exam_card(exam)
            if st.button("প্রশ্ন দেখুন", key=f"open_{exam['id']}", use_container_width=True):
                st.session_state["selected_exam_id"] = exam["id"]
                st.rerun()
        if len(exams) > 80:
            st.caption("প্রথম ৮০টি পরীক্ষা দেখানো হচ্ছে। ফিল্টার ব্যবহার করে সংখ্যা কমিয়ে আনুন।")

    with right:
        selected_id = st.session_state.get("selected_exam_id")
        if search.strip():
            st.subheader(f"প্রশ্নে অনুসন্ধান: “{search.strip()}”")
            hits = search_questions(search.strip(), tuple(selected_categories), year)
            if not hits:
                st.info("মিলে যাওয়া প্রশ্ন পাওয়া যায়নি।")
            for q in hits:
                st.markdown(
                    f"<div class='exam-meta'>{html.escape(q['exam_name'])} · "
                    f"{html.escape(str(q.get('exam_date') or ''))}</div>",
                    unsafe_allow_html=True,
                )
                render_question(q, True)
            return

        if not selected_id:
            st.subheader("প্রশ্ন দেখতে একটি পরীক্ষা বেছে নিন")
            st.markdown(
                "<div class='source-note'>বাম দিকের তালিকা থেকে যেকোনো পরীক্ষা খুলুন। "
                "প্রতিটি প্রশ্নের উত্তর আলাদাভাবে দেখানো যায়; অনুশীলন মোডে উত্তর লুকানো থাকে।</div>",
                unsafe_allow_html=True,
            )
            return

        exam = load_exam(int(selected_id))
        if exam is None:
            st.warning("পরীক্ষাটি পাওয়া যায়নি।")
            return
        questions = load_questions(exam["id"])
        st.subheader(exam["exam_name"])
        st.markdown(
            f"{coverage_badge(exam['coverage_status'])} {source_badge(exam.get('content_source'))} "
            f"<span class='exam-meta'>{html.escape(str(exam.get('exam_date') or ''))} · "
            f"{html.escape(exam.get('category_names') or '')} · "
            f"প্রশ্ন {exam.get('collected_questions')}/{exam.get('total_questions')} · "
            f"উত্তর {exam.get('answered_questions')}</span>",
            unsafe_allow_html=True,
        )
        if exam["coverage_status"] != "full":
            st.markdown(
                f"<div class='notice'>এই পরীক্ষার সম্পূর্ণ প্রশ্নপত্র পাওয়া যায়নি। "
                f"সংগৃহীত {exam.get('collected_questions')}টি প্রশ্নের মধ্যে "
                f"{exam.get('answered_questions')}টির উত্তর প্রকাশিত আছে।</div>",
                unsafe_allow_html=True,
            )
        if exam.get("source_url"):
            st.markdown(f"উৎস: [{exam['source_url']}]({exam['source_url']})")

        show_answers = st.toggle("উত্তর দেখাও", value=False, key=f"show_{exam['id']}")
        practice = st.toggle("অনুশীলন মোড", value=False, key=f"practice_{exam['id']}")

        if practice and not show_answers:
            with st.form(f"practice_form_{exam['id']}"):
                picks: dict[int, int] = {}
                for q in questions:
                    options = [q.get(f"option_{i}") or "" for i in range(1, 5)]
                    labels = [f"(ক) {options[0]}", f"(খ) {options[1]}",
                              f"(গ) {options[2]}", f"(ঘ) {options[3]}"]
                    choice = st.radio(
                        f"{q['question_no']}. {q['question_text']}",
                        options=range(1, 5), format_func=lambda i, l=labels: l[i - 1],
                        index=None, key=f"pick_{exam['id']}_{q['question_no']}",
                    )
                    picks[q["question_no"]] = choice
                submitted = st.form_submit_button("উত্তর জমা দিন", use_container_width=True)
            if submitted:
                correct = 0
                answered = 0
                for q in questions:
                    pick = picks.get(q["question_no"])
                    if pick and q["answer_index"] in (1, 2, 3, 4):
                        answered += 1
                        if pick == q["answer_index"]:
                            correct += 1
                st.success(f"সঠিক উত্তর: {correct} / {answered} (উত্তর দেওয়া হয়েছে {answered}টি)")
                for q in questions:
                    render_question(q, True)
            return

        for q in questions:
            render_question(q, show_answers)


def render_coverage() -> None:
    st.subheader("কভারেজ রিপোর্ট")
    st.markdown(
        "<div class='source-note'>প্রতিটি পরীক্ষার জন্য কতটি প্রশ্ন সংগ্রহ করা গেছে এবং "
        "কতটির উত্তর প্রকাশিত আছে তা এখানে দেখানো হয়। যেখানে সম্পূর্ণ সেট পাওয়া যায়নি, "
        "সেখানে ‘আংশিক’ বা ‘ফলব্যাক ১৫’ লেখা থাকে।</div>",
        unsafe_allow_html=True,
    )
    rows = load_coverage()
    st.dataframe(
        [
            {
                "বিভাগ": r["category"],
                "পরীক্ষা": r["exams"],
                "প্রশ্ন": r["questions"],
                "উত্তরসহ": r["answered"] or 0,
            }
            for r in rows
        ],
        use_container_width=True,
        hide_index=True,
    )


def render_sources() -> None:
    st.subheader("উৎস, অনুমতি ও সীমাবদ্ধতা")
    st.markdown(
        """
        <div class="source-note">
        <b>উৎস:</b> SattAcademy (public job-solution pages), Live MCQ (approved public solution pages)।
        JobsNoticeBD-এর ২০২৫–২০২৬ পেজগুলো শুধু ছবি হিসেবে পাওয়া গেছে, তাই টেক্সট প্রশ্ন হিসেবে নেওয়া হয়নি।<br><br>
        <b>সীমাবদ্ধতা:</b> SattAcademy প্রতিটি পরীক্ষার প্রথম পেজে শুধু ১৫টি MCQ প্রকাশ করে; পরবর্তী পেজ robots.txt দ্বারা নিষিদ্ধ।
        তাই কোনো পরীক্ষার জন্য পূর্ণ সেট না পাওয়া গেলে সেখানে ১৫টি প্রশ্ন (fallback) দেখানো হয় এবং ‘আংশিক’ লেবেল দেওয়া হয়।<br><br>
        <b>উত্তর:</b> শুধুমাত্র উৎসে প্রকাশিত উত্তর সংরক্ষণ করা হয়। কোনো উত্তর অনুমান করা হয় না; উত্তর না থাকলে
        ‘উত্তর প্রকাশিত হয়নি’ দেখানো হয়। ব্যাখ্যা প্রকাশ করা হয় না।<br><br>
        <b>স্বত্ব:</b> প্রশ্নের স্বত্ব সংশ্লিষ্ট উৎসের। এই অ্যাপ শুধু উদ্ধৃতি ও লিংকসহ শিক্ষামূলক সংগ্রহ দেখায়।
        </div>
        """,
        unsafe_allow_html=True,
    )
    summary = load_summary()
    st.caption(f"সর্বশেষ আপডেট: {summary['last_update']} · সংকলন: চাকরি পরীক্ষার MCQ প্রশ্নব্যাংক")


def main() -> None:
    inject_css()
    if not db_available():
        st.error(
            "`job_archive.db` পাওয়া যায়নি। প্রথমে `python -m job_scraper scrape`, "
            "তারপর `python sync_db.py` চালান।"
        )
        return

    summary = load_summary()
    render_header(summary)
    categories = load_categories()
    institutions = load_institutions()

    tab_library, tab_coverage, tab_sources = st.tabs(
        ["প্রশ্নব্যাংক", "কভারেজ", "উৎস ও নীতি"]
    )
    with tab_library:
        render_library(summary, categories, institutions)
    with tab_coverage:
        render_coverage()
    with tab_sources:
        render_sources()


main()
