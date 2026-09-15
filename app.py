"""Board Exams Question Bank UI (SSC/HSC, subject/board/year/type filters).

Matches the sattacademy.com/board-exams filter header from the screenshots:
  Row1: [Level] [Subject] [Board]
  Row2: [Type] [Year] [Search]
  Toggle: [Board Exams | Test Papers] + pdf/share buttons.

Reads from the local SQLite DB (board_exams + exam_questions tables).
Run: streamlit run app.py
"""

from __future__ import annotations

import html
import json
import sqlite3
from pathlib import Path

import streamlit as st

DB_PATH = Path(__file__).with_name("ssc_archive.db")

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
def get_conn() -> sqlite3.Connection | None:
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def load_filter_values(conn: sqlite3.Connection, class_key: str):
    cur = conn.cursor()
    cur.execute(
        "SELECT DISTINCT subject FROM board_exams WHERE class_key=? AND subject IS NOT NULL ORDER BY subject",
        (class_key,),
    )
    subjects = [r[0] for r in cur.fetchall() if r[0]]
    cur.execute(
        "SELECT DISTINCT board FROM board_exams WHERE class_key=? AND board IS NOT NULL ORDER BY board",
        (class_key,),
    )
    boards = [r[0] for r in cur.fetchall() if r[0]]
    cur.execute(
        "SELECT DISTINCT year FROM board_exams WHERE class_key=? AND year IS NOT NULL ORDER BY year DESC",
        (class_key,),
    )
    years = [str(r[0]) for r in cur.fetchall() if r[0]]
    return subjects, boards, years


def query_exams(conn, class_key, subject, board, qtype, year, search, limit=200):
    clauses = ["class_key = ?"]
    params: list = [class_key]
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
        clauses.append("(mcq_count IS NOT NULL AND mcq_count > 0)")
    elif qtype == "CQ":
        clauses.append("(cq_count IS NOT NULL AND cq_count > 0)")
    if search:
        clauses.append("(exam_name LIKE ? OR subject LIKE ? OR mcq_url LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like, like])
    where = " AND ".join(clauses)
    cur = conn.cursor()
    cur.execute(
        f"SELECT * FROM board_exams WHERE {where} ORDER BY year DESC, subject LIMIT ?",
        (*params, limit),
    )
    return [dict(r) for r in cur.fetchall()]


def load_questions(conn, exam_id: int):
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM exam_questions WHERE exam_id=? ORDER BY question_type, question_no",
        (exam_id,),
    )
    return [dict(r) for r in cur.fetchall()]


def parse_options(row: dict):
    try:
        data = json.loads(row.get("options_json") or "{}")
    except (TypeError, ValueError):
        return [], [], {}
    if isinstance(data, list):  # legacy safety
        return data, [], {}
    return data.get("options", []), data.get("images", []), data


# ---------------------------------------------------------------- pdf export
def build_print_html(exam: dict, questions: list[dict]) -> str:
    title = html.escape(exam.get("exam_name") or exam.get("subject") or "Board Exam")
    parts = [
        f"<h1>{title} — {exam.get('board')} {exam.get('year')}</h1>",
        f"<p>Source: {html.escape(exam.get('mcq_url') or '')} | "
        f"{html.escape(exam.get('written_url') or '')}</p><hr/>",
    ]
    for q in questions:
        opts, imgs, _meta = parse_options(q)
        parts.append(f"<h3>Q{q['question_no']} ({q['question_type']})</h3>")
        parts.append(f"<p>{html.escape(q.get('question_text') or '')}</p>")
        for src in imgs:
            parts.append(f'<img src="{html.escape(src)}" style="max-width:400px"/><br/>')
        for o in opts:
            if isinstance(o, dict):
                parts.append(f"<p>{o.get('index')}. {html.escape(o.get('text') or '')}</p>")
        if q.get("answer"):
            parts.append(f"<p><b>Answer: {html.escape(str(q['answer']))}</b></p>")
        parts.append("<hr/>")
    return "<html><body>" + "".join(parts) + "</body></html>"


# ---------------------------------------------------------------- ui
st.set_page_config(page_title="Board Exams Question Bank", layout="wide")

st.markdown(
    """
<style>
.block-container {padding-top: 1rem; max-width: 1200px;}
.header-bar {background: #16191d; border-radius: 8px 8px 0 0; padding: 14px 18px; color: #fff;}
.header-bar h2 {text-align: center; font-size: 20px; margin: 0; color: #fff;}
.filter-bar {background: #1d2126; border-radius: 0 0 8px 8px; padding: 16px;}
.filter-bar select, .filter-bar input {background: #2a2f36 !important; color: #fff !important;
  border: 1px solid #3a4048 !important; border-radius: 6px !important;}
.toggle-green {background: #0d9d58; color: #fff; border-radius: 20px; padding: 6px 18px; border: none;}
.toggle-grey {background: #3a4048; color: #fff; border-radius: 20px; padding: 6px 18px; border: none;}
.exam-card {background: #1d2126; border: 1px solid #2e343c; border-radius: 8px; padding: 14px 16px; margin: 10px 0; color:#eee;}
.exam-card a {color: #4da3ff;}
.q-card {background: #22262c; border: 1px solid #333a43; border-radius: 8px; padding: 12px 14px; margin: 8px 0; color:#eee;}
</style>
""",
    unsafe_allow_html=True,
)

conn = get_conn()
if conn is None:
    st.error(f"Database not found at {DB_PATH}. Run the scraper first: python -m ssc_scraper scrape --source sattacademy --limit 20")
    st.stop()

# ---- header (matches screenshots) ----
level_ui = st.session_state.get("level_ui", "SSC")
level_bn = LEVEL_LABELS[LEVEL_TO_KEY[level_ui]]
header_html = f"""
<div class="header-bar">
  <div style="display:flex; justify-content:space-between; align-items:center;">
    <span title="Board question bank info" style="background:#3a4048;border-radius:50%;width:28px;height:28px;display:inline-flex;align-items:center;justify-content:center;">i</span>
    <h2>{level_bn} সকল বোর্ড পরীক্ষার প্রশ্নপত্র ও ডিজিটাল প্র্যাকটিস হাব</h2>
    <span>
      <span style="background:#2a2f36;border-radius:6px;padding:4px 10px;">🖨 pdf</span>
      <span style="margin-left:10px;">🔗</span>
    </span>
  </div>
</div>
"""
st.markdown(header_html, unsafe_allow_html=True)

# ---- filters ----
st.markdown('<div class="filter-bar">', unsafe_allow_html=True)
c1, c2, c3 = st.columns(3)
with c1:
    level_ui = st.selectbox("Level", LEVEL_OPTIONS, index=LEVEL_OPTIONS.index(level_ui), key="level_ui", label_visibility="collapsed")
with c2:
    subject_ui = st.selectbox("Subject", ["All Subject"], key="subject_ui", label_visibility="collapsed")
with c3:
    board_ui = st.selectbox("Board", ["All board"], key="board_ui", label_visibility="collapsed")
c4, c5, c6 = st.columns(3)
with c4:
    type_ui = st.selectbox("Type", TYPE_OPTIONS, key="type_ui", label_visibility="collapsed")
with c5:
    year_ui = st.selectbox("Year", YEAR_OPTIONS, key="year_ui", label_visibility="collapsed")
with c6:
    search_ui = st.text_input("Search", placeholder="এক্সাম সার্চ করুন...", key="search_ui", label_visibility="collapsed")
st.markdown('</div>', unsafe_allow_html=True)

class_key = LEVEL_TO_KEY[level_ui]
subjects_db, boards_db, years_db = load_filter_values(conn, class_key)
# refresh dropdown options while preserving selection
subject_opts = ["All Subject"] + subjects_db
board_opts = ["All board"] + boards_db
year_opts = ["All Year"] + (years_db or [y for y in [str(v) for v in range(2026, 2014, -1)]])
# Streamlit needs key-based update; use sidebar-free rerun-safe approach:
subject_ui = st.selectbox("Subject ", subject_opts, key="subject_sel")
board_ui = st.selectbox("Board ", board_opts, key="board_sel")
year_sel = st.selectbox("Year ", year_opts, key="year_sel")

# ---- toggle ----
t1, t2, t3 = st.columns([1, 1, 4])
with t1:
    mode = st.radio("mode", ["Board Exams", "Test Papers"], horizontal=True, label_visibility="collapsed")
if mode == "Test Papers":
    st.info("Test Papers source is not part of v1 (board-exams only). Toggle back to Board Exams.")
    st.stop()

# ---- results ----
qtype_map = {"All Types": "all", "MCQ": "MCQ", "CQ": "CQ", "MCQ+CQ": "all"}
exams = query_exams(conn, class_key, subject_ui, board_ui, qtype_map[type_ui], year_sel, search_ui.strip())
st.write(f"**{len(exams)}** exam(s) — {level_bn} | {subject_ui} | {board_ui} | {type_ui} | {year_sel}")

for exam in exams:
    mcq_n = exam.get("mcq_count") or 0
    cq_n = exam.get("cq_count") or 0
    with st.container():
        st.markdown('<div class="exam-card">', unsafe_allow_html=True)
        st.markdown(f"### {html.escape(exam.get('exam_name') or '')}")
        st.caption(f"{LEVEL_LABELS.get(exam.get('class_key') or class_key, '')} | {exam.get('board')} | {exam.get('year')}")
        mcq_link = exam.get("mcq_url") or ""
        written_link = exam.get("written_url") or ""
        link_line = []
        if mcq_n:
            link_line.append(f"[MCQ {mcq_n}]({mcq_link})")
        if cq_n:
            link_line.append(f"[CQ {cq_n}]({written_link})")
        st.markdown(" | ".join(link_line) if link_line else "No questions yet")
        with st.expander("View questions (page-1, robots-limited)"):
            questions = load_questions(conn, exam["id"])
            if not questions:
                st.warning("No questions collected yet for this exam. Run the scraper for this board/year.")
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
                    st.image(src, width=300)
                for o in opts:
                    if isinstance(o, dict):
                        st.write(f"{o.get('index')}. {o.get('text')}")
                        for oi in o.get("images", []) or []:
                            st.image(oi, width=250)
                if q.get("answer"):
                    st.success(f"Answer: {q['answer']}")
                if meta.get("question_href"):
                    st.caption(meta["question_href"])
                st.markdown('</div>', unsafe_allow_html=True)
            if questions:
                print_html = build_print_html(exam, questions)
                st.download_button(
                    "⬇ PDF / Print (HTML)",
                    data=print_html.encode("utf-8"),
                    file_name=f"{exam.get('board')}_{exam.get('year')}_{exam.get('subject')}_exam{exam['id']}.html",
                    mime="text/html",
                    key=f"dl_{exam['id']}",
                )
        st.markdown('</div>', unsafe_allow_html=True)

conn.close()
