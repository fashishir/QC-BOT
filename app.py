"""Board Exams & Test Papers Question Bank UI (SSC/HSC, subject/board/year/type filters).

Reads from board_questions.db (exams + questions tables) with fallback to ssc_archive.db.
Run: streamlit run app.py
"""

from __future__ import annotations

import html
import json
import logging
import sqlite3
import urllib.request
from pathlib import Path

import streamlit as st

from ssc_scraper.pdf_export import build_export_payload, html_to_pdf

log = logging.getLogger(__name__)

st.set_page_config(page_title="Board Exams Question Bank", layout="wide")

LEVEL_LABELS = {
    "ssc": "এসএসসি",
    "dakhil": "দাখিল",
    "hsc": "এইচএসসি",
}
LEVEL_OPTIONS = ["SSC", "HSC", "Dakhil"]
LEVEL_TO_KEY = {"SSC": "ssc", "HSC": "hsc", "Dakhil": "dakhil"}

TYPE_OPTIONS = ["All Types", "MCQ", "CQ", "MCQ+CQ"]
YEAR_OPTIONS = ["All Year"] + [str(y) for y in range(2026, 2014, -1)]


# ---------------------------------------------------------------- db helpers
def get_db_path() -> Path:
    # Prefer newly scraped board_questions.db, fallback to ssc_archive.db
    p1 = Path(__file__).resolve().parent / "board_questions.db"
    if p1.exists() and p1.stat().st_size > 0:
        return p1
    p2 = Path(__file__).resolve().parent / "ssc_archive.db"
    return p2


def get_conn() -> sqlite3.Connection | None:
    db_path = get_db_path()
    if not db_path.exists() or db_path.stat().st_size == 0:
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception:
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            return conn
        except Exception as exc:
            st.error(f"Error opening database at {db_path}: {exc}")
            return None


def get_table_names(conn: sqlite3.Connection) -> tuple[str, str]:
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]
    exams_tbl = "exams" if "exams" in tables else "board_exams"
    qs_tbl = "questions" if "questions" in tables else "exam_questions"
    return exams_tbl, qs_tbl


def load_filter_values(conn: sqlite3.Connection, exams_tbl: str, class_key: str):
    cur = conn.cursor()
    cur.execute(
        f"SELECT DISTINCT subject FROM {exams_tbl} WHERE class_key=? AND subject IS NOT NULL ORDER BY subject",
        (class_key,),
    )
    subjects = [r[0] for r in cur.fetchall() if r[0]]
    cur.execute(
        f"SELECT DISTINCT board FROM {exams_tbl} WHERE class_key=? AND board IS NOT NULL ORDER BY board",
        (class_key,),
    )
    boards = [r[0] for r in cur.fetchall() if r[0]]
    cur.execute(
        f"SELECT DISTINCT year FROM {exams_tbl} WHERE class_key=? AND year IS NOT NULL ORDER BY year DESC",
        (class_key,),
    )
    years = [str(r[0]) for r in cur.fetchall() if r[0]]
    return subjects, boards, years


def query_exams(conn, exams_tbl, class_key, subject, board, qtype, year, search, source_mode="board-exam", limit=2000):
    cur = conn.cursor()
    clauses = ["class_key = ?"]
    params: list = [class_key]

    # Check if source_type column exists
    cols = [r[1] for r in cur.execute(f"PRAGMA table_info({exams_tbl})").fetchall()]
    if "source_type" in cols and source_mode:
        clauses.append("source_type = ?")
        params.append(source_mode)

    if subject != "All Subject":
        clauses.append("subject = ?")
        params.append(subject)
    if board != "All board":
        clauses.append("board = ?")
        params.append(board)
    if year != "All Year":
        clauses.append("year = ?")
        params.append(int(year))
    if qtype == "MCQ":
        clauses.append("((mcq_count IS NOT NULL AND mcq_count > 0) OR (mcq_url IS NOT NULL))")
    elif qtype == "CQ":
        clauses.append("((cq_count IS NOT NULL AND cq_count > 0) OR (written_url IS NOT NULL))")
    if search:
        clauses.append("(exam_name LIKE ? OR subject LIKE ? OR mcq_url LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like, like])

    where = " AND ".join(clauses)
    cur.execute(
        f"SELECT * FROM {exams_tbl} WHERE {where} ORDER BY year DESC, exam_name LIMIT ?",
        (*params, limit),
    )
    return [dict(r) for r in cur.fetchall()]


def load_questions(conn, qs_tbl: str, exam_id: int):
    cur = conn.cursor()
    cur.execute(
        f"SELECT * FROM {qs_tbl} WHERE exam_id=? ORDER BY question_type, question_no",
        (exam_id,),
    )
    return [dict(r) for r in cur.fetchall()]


def parse_options(row: dict):
    try:
        data = json.loads(row.get("options_json") or "[]")
    except (TypeError, ValueError):
        return [], [], {}
    if isinstance(data, list):
        # Format: [{"index": 1, "text": "...", "images": [...]}]
        return data, [], {}
    return data.get("options", []), data.get("images", []), data


# ---------------------------------------------------------------- pdf export
# NOTE: html_to_pdf / build_print_html live in ssc_scraper.pdf_export so they
# stay importable/testable without running the Streamlit UI. Re-exported here
# for backward compatibility with any external callers.
from ssc_scraper.pdf_export import build_print_html as build_print_html  # noqa: F401,E402


@st.cache_data(show_spinner=False)
def _cached_html_to_pdf(html_content: str) -> bytes | None:
    """Cache PDF renders across Streamlit reruns (WeasyPrint is ~0.5-1s/doc)."""
    return html_to_pdf(html_content)


# ---------------------------------------------------------------- ui
st.markdown(
    """
<style>
.block-container {padding-top: 1rem; max-width: 1200px;}
.header-bar {background: #16191d; border-radius: 8px 8px 0 0; padding: 14px 18px; color: #fff;}
.header-bar h2 {text-align: center; font-size: 20px; margin: 0; color: #fff;}
.filter-bar {background: #1d2126; border-radius: 0 0 8px 8px; padding: 16px;}
.exam-card {background: #1d2126; border: 1px solid #2e343c; border-radius: 8px; padding: 14px 16px; margin: 10px 0; color:#eee;}
.exam-card a {color: #4da3ff;}
.q-card {background: #22262c; border: 1px solid #333a43; border-radius: 8px; padding: 12px 14px; margin: 8px 0; color:#eee;}
</style>
""",
    unsafe_allow_html=True,
)

conn = get_conn()
if conn is None:
    st.error("Database not found. Please run `python scraper.py` first.")
    st.stop()

exams_tbl, qs_tbl = get_table_names(conn)

# Header
level_ui = st.session_state.get("level_sel", "SSC")
if level_ui not in LEVEL_OPTIONS:
    level_ui = "SSC"
class_key = LEVEL_TO_KEY[level_ui]
level_bn = LEVEL_LABELS[class_key]

header_html = f"""
<div class="header-bar">
  <div style="display:flex; justify-content:space-between; align-items:center;">
    <span style="background:#3a4048;border-radius:50%;width:28px;height:28px;display:inline-flex;align-items:center;justify-content:center;">i</span>
    <h2>{level_bn} সকল বোর্ড ও টেস্ট পেপারের প্রশ্নপত্র ও ডিজিটাল হাব</h2>
    <span>
      <span style="background:#2a2f36;border-radius:6px;padding:4px 10px;">PDF Export</span>
    </span>
  </div>
</div>
"""
st.markdown(header_html, unsafe_allow_html=True)

# Pre-load filter options from DB for selected level
subjects_db, boards_db, years_db = load_filter_values(conn, exams_tbl, class_key)
subject_opts = ["All Subject"] + subjects_db
board_opts = ["All board"] + boards_db
year_opts = ["All Year"] + (years_db if years_db else [str(y) for y in range(2026, 2014, -1)])

# ---- filters ----
st.markdown('<div class="filter-bar">', unsafe_allow_html=True)
c1, c2, c3 = st.columns(3)
with c1:
    level_ui = st.selectbox(
        "Level",
        LEVEL_OPTIONS,
        index=LEVEL_OPTIONS.index(level_ui),
        key="level_sel",
        label_visibility="collapsed",
    )
with c2:
    subject_ui = st.selectbox(
        "Subject",
        subject_opts,
        key=f"subject_sel_{level_ui}",
        label_visibility="collapsed",
    )
with c3:
    board_ui = st.selectbox(
        "Board",
        board_opts,
        key=f"board_sel_{level_ui}",
        label_visibility="collapsed",
    )

c4, c5, c6 = st.columns(3)
with c4:
    type_ui = st.selectbox("Type", TYPE_OPTIONS, key="type_sel", label_visibility="collapsed")
with c5:
    year_sel = st.selectbox("Year", year_opts, key=f"year_sel_{level_ui}", label_visibility="collapsed")
with c6:
    search_ui = st.text_input(
        "Search",
        placeholder="এক্সাম সার্চ করুন...",
        key="search_sel",
        label_visibility="collapsed",
    )
st.markdown("</div>", unsafe_allow_html=True)

# ---- Mode Toggle ----
t1, t2 = st.columns([1, 4])
with t1:
    mode = st.radio("mode", ["Board Exams", "Test Papers"], horizontal=True, label_visibility="collapsed")
source_mode = "board-exam" if mode == "Board Exams" else "test-paper"

# ---- Results ----
qtype_map = {"All Types": "all", "MCQ": "MCQ", "CQ": "CQ", "MCQ+CQ": "all"}
exams = query_exams(conn, exams_tbl, class_key, subject_ui, board_ui, qtype_map[type_ui], year_sel, search_ui.strip(), source_mode=source_mode)
st.write(f"**{len(exams)}** exam(s) found — {level_bn} | {mode} | {subject_ui} | {board_ui} | {year_sel}")

if not exams:
    st.info("কোনো পরীক্ষা পাওয়া যায়নি। ডেটা সংগ্রহ করতে `python scraper.py` চালান।")

for exam in exams:
    mcq_n = exam.get("mcq_count") or 0
    cq_n = exam.get("cq_count") or 0
    with st.container():
        st.markdown('<div class="exam-card">', unsafe_allow_html=True)
        st.markdown(f"### {html.escape(exam.get('exam_name') or '')}")
        st.caption(f"{LEVEL_LABELS.get(exam.get('class_key') or class_key, '')} | {exam.get('board')} | {exam.get('year')} | {exam.get('source_type', 'board-exam')}")
        mcq_link = exam.get("mcq_url") or ""
        written_link = exam.get("written_url") or ""
        link_line = []
        if mcq_link:
            link_line.append(f"[MCQ {mcq_n if mcq_n else ''}]({mcq_link})")
        if written_link:
            link_line.append(f"[CQ {cq_n if cq_n else ''}]({written_link})")
        st.markdown(" | ".join(link_line) if link_line else "Source available")
        
        with st.expander("View questions"):
            questions = load_questions(conn, qs_tbl, exam["id"])
            if not questions:
                st.warning("No questions collected yet for this exam.")
            show = type_ui
            for q in questions:
                if show == "MCQ" and q["question_type"] != "mcq":
                    continue
                if show == "CQ" and q["question_type"] != "written":
                    continue
                opts, imgs, meta = parse_options(q)
                st.markdown('<div class="q-card">', unsafe_allow_html=True)
                st.markdown(f"**Q{q['question_no']} [{q['question_type']}]** {q.get('question_text') or ''}")
                for src in imgs:
                    st.caption(f"[Image: {src}]")
                for o in opts:
                    if isinstance(o, dict):
                        st.write(f"{o.get('index')}. {o.get('text')}")
                ans = q.get("correct_answer") or q.get("answer")
                if ans:
                    st.success(f"Answer: {ans}")
                st.markdown('</div>', unsafe_allow_html=True)
            if questions:
                payload = build_export_payload(exam, questions, pdf_converter=_cached_html_to_pdf)
                st.download_button(
                    payload["label"],
                    data=payload["data"],
                    file_name=payload["file_name"],
                    mime=payload["mime"],
                    key=f"dl_{exam['id']}",
                )
                if not payload["is_pdf"]:
                    st.caption("PDF engine unavailable — serving printable HTML instead.")
        st.markdown('</div>', unsafe_allow_html=True)

conn.close()
