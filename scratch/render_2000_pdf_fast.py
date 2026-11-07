import os
import csv
import html
import subprocess
import tempfile
import pymupdf

OPTION_SYMBOLS = {1: "(ক)", 2: "(খ)", 3: "(গ)", 4: "(ঘ)"}

csv_path = "2025_2026_Job_Exam_MCQ_2000_With_Explanation.csv"
pdf_final_path = "2025_2026_Job_Exam_MCQ_2000_With_Explanation.pdf"

# Read all 2000 rows from CSV
with open(csv_path, "r", encoding="utf-8-sig") as fp:
    reader = csv.DictReader(fp)
    questions = list(reader)

print(f"Read {len(questions)} questions from {csv_path}")

# Group by exam
exams_order = []
exams_map = {}
for q in questions:
    ename = q["exam_name"]
    if ename not in exams_map:
        exams_order.append(ename)
        exams_map[ename] = {
            "meta": {
                "name": ename,
                "date": q["exam_date"],
                "year": q["year"],
                "category": q["category"],
                "institution": q["institution"],
                "source_url": q["source_url"],
            },
            "questions": [],
        }
    exams_map[ename]["questions"].append(q)

edge_bin = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not os.path.exists(edge_bin):
    edge_bin = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"

profile_dir = os.path.join(tempfile.gettempdir(), "edge_fast_render")
os.makedirs(profile_dir, exist_ok=True)

temp_dir = os.path.join(tempfile.gettempdir(), "mcq_chunks")
os.makedirs(temp_dir, exist_ok=True)

def render_html_to_pdf(html_text: str, out_pdf: str) -> bool:
    in_html = out_pdf.replace(".pdf", ".html")
    with open(in_html, "w", encoding="utf-8") as f:
        f.write(html_text)
    cmd = [
        edge_bin,
        "--headless",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--user-data-dir={profile_dir}",
        f"--print-to-pdf={os.path.abspath(out_pdf)}",
        f"file:///{os.path.abspath(in_html).replace('\\', '/')}"
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return os.path.exists(out_pdf) and os.path.getsize(out_pdf) > 0

css_base = """
@page { size: A4; margin: 12mm 10mm 14mm 10mm; }
body { font-family: 'Nirmala UI', 'Kalpurush', 'SolaimanLipi', sans-serif; font-size: 9.8pt; line-height: 1.55; color: #1e293b; background: #ffffff; margin: 0; padding: 0; }
.cover-page { text-align: center; padding: 40px 20px 20px; }
.cover-badge { display: inline-block; background: #0284c7; color: #ffffff; padding: 6px 18px; border-radius: 20px; font-size: 11pt; font-weight: bold; margin-bottom: 20px; }
.cover-title { font-size: 24pt; font-weight: 800; color: #0b3b6f; margin: 10px 0 15px; line-height: 1.3; }
.cover-subtitle { font-size: 13pt; color: #334155; margin-bottom: 25px; line-height: 1.6; }
.cover-stats { background: #f0fdf4; border: 2px solid #86efac; border-radius: 12px; padding: 18px 25px; display: inline-block; text-align: left; margin-bottom: 30px; }
.cover-stats-item { font-size: 11pt; color: #166534; margin: 6px 0; font-weight: 600; }
.cover-toc { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 16px 20px; text-align: left; max-width: 640px; margin: 0 auto; }
.cover-toc h3 { margin: 0 0 10px; color: #0b3b6f; font-size: 12pt; border-bottom: 2px solid #cbd5e1; padding-bottom: 5px; }
.cover-toc table { width: 100%; border-collapse: collapse; font-size: 9.2pt; }
.cover-toc th { text-align: left; color: #475569; padding: 4px 6px; border-bottom: 1px solid #cbd5e1; }
.cover-toc td { padding: 4px 6px; border-bottom: 1px solid #f1f5f9; }
.exam-header { margin-top: 5px; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 2px solid #0284c7; }
.exam-title { font-size: 14pt; font-weight: bold; color: #0b3b6f; margin: 0 0 5px; }
.exam-meta { font-size: 8.8pt; color: #64748b; }
.question-card { border: 1px solid #e2e8f0; border-radius: 6px; padding: 7px 10px; margin-bottom: 8px; page-break-inside: avoid; background: #ffffff; }
.q-stem { font-weight: 700; color: #0f172a; margin-bottom: 5px; font-size: 9.8pt; }
.q-num { color: #0284c7; font-weight: 800; margin-right: 4px; }
.options-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 3px 12px; margin-bottom: 5px; font-size: 9.2pt; }
.opt { color: #334155; }
.opt-correct { color: #166534; font-weight: 700; }
.ans-pill { display: inline-block; background: #dcfce7; color: #15803d; border: 1px solid #86efac; border-radius: 4px; padding: 2px 7px; font-size: 8.6pt; font-weight: bold; margin-bottom: 4px; }
.expl-box { background: #f8fafc; border-left: 3px solid #0284c7; padding: 5px 9px; border-radius: 3px; font-size: 8.6pt; line-height: 1.5; color: #334155; margin-top: 3px; }
.expl-title { font-weight: 700; color: #0369a1; }
"""

# 1. Render Cover Page
cover_html = f"""<!DOCTYPE html><html lang='bn'><head><meta charset='utf-8'><style>{css_base}</style></head><body>
<div class='cover-page'>
<div class='cover-badge'>২০২৫–২০২৬ চাকরি পরীক্ষার প্রামাণ্য প্রশ্নব্যাংক</div>
<div class='cover-title'>চাকরি পরীক্ষার MCQ প্রশ্নব্যাংক<br>ব্যাখ্যাসহ ২০০০ প্রশ্ন ও উত্তর</div>
<div class='cover-subtitle'>বিসিএস প্রিলিমিনারি, বিশেষ বিসিএস, সরকারি ব্যাংক, শিক্ষক নিবন্ধন ও বিভিন্ন মন্ত্রণালয়ের চাকরি পরীক্ষার সম্পূর্ণ প্রশ্নোত্তর ও প্রামাণ্য ব্যাখ্যা</div>
<div class='cover-stats'>
<div class='cover-stats-item'>✓ মোট প্রশ্ন: ২০০০ টি বহুনির্বাচনী প্রশ্ন (MCQ)</div>
<div class='cover-stats-item'>✓ পরীক্ষার বছর: ২০২৫ ও ২০২৬</div>
<div class='cover-stats-item'>✓ প্রতিটি প্রশ্নের সঠিক উত্তর ও বিস্তারিত ব্যাখ্যা (Explanation) সহ</div>
<div class='cover-stats-item'>✓ মূল ডাটা সোর্স: Live MCQ™ Authentic Solutions</div>
</div>
<div class='cover-toc'>
<h3>সূচিপত্র ও পরীক্ষার পরিসংখ্যান</h3>
<table>
<thead><tr><th>পরীক্ষার নাম</th><th>তারিখ</th><th>বছর</th><th style='text-align:right'>প্রশ্ন</th></tr></thead>
<tbody>
"""
for ename in exams_order:
    m = exams_map[ename]["meta"]
    cnt = len(exams_map[ename]["questions"])
    cover_html += f"<tr><td><b>{html.escape(m['name'])}</b></td><td>{m['date']}</td><td>{m['year']}</td><td style='text-align:right'><b>{cnt}</b></td></tr>"

cover_html += "</tbody></table></div></div></body></html>"

cover_pdf = os.path.join(temp_dir, "cover.pdf")
print("Rendering Cover PDF...")
render_html_to_pdf(cover_html, cover_pdf)

# 2. Render each exam batch
pdf_parts = [cover_pdf]

for idx, ename in enumerate(exams_order, 1):
    einfo = exams_map[ename]
    m = einfo["meta"]
    qs = einfo["questions"]
    part_html = f"<!DOCTYPE html><html lang='bn'><head><meta charset='utf-8'><style>{css_base}</style></head><body>"
    part_html += "<div class='exam-header'>"
    part_html += f"<div class='exam-title'>{html.escape(m['name'])}</div>"
    part_html += (
        f"<div class='exam-meta'>তারিখ: {m['date']} &nbsp;|&nbsp; বছর: {m['year']} &nbsp;|&nbsp; "
        f"প্রতিষ্ঠান/ক্যাটাগরি: {html.escape(m['category'])} &nbsp;|&nbsp; "
        f"প্রশ্ন সংখ্যা: {len(qs)} টি &nbsp;|&nbsp; উৎস: {html.escape(m['source_url'])}</div>"
    )
    part_html += "</div>"

    for q in qs:
        s_no = q["serial_no"]
        q_text = html.escape(q["question_text"])
        cor_char = q["correct_option"]
        cor_ans_text = html.escape(q["correct_answer_text"])
        expl = html.escape(q["explanation"]).replace("\n", "<br>")

        opt_html = []
        for i in range(1, 5):
            sym = OPTION_SYMBOLS[i]
            otext = html.escape(q[f"option_{i}"])
            is_cor = (q.get("correct_option") == ["ক", "খ", "গ", "ঘ"][i-1])
            cls = "opt-correct" if is_cor else "opt"
            check_mark = " ✓" if is_cor else ""
            opt_html.append(f"<div class='{cls}'>{sym} {otext}{check_mark}</div>")

        card = (
            f"<div class='question-card'>"
            f"<div class='q-stem'><span class='q-num'>[{s_no}]</span> {q_text}</div>"
            f"<div class='options-grid'>{''.join(opt_html)}</div>"
            f"<div class='ans-pill'>সঠিক উত্তর: ({cor_char}) {cor_ans_text}</div>"
            f"<div class='expl-box'><span class='expl-title'>ব্যাখ্যা: </span>{expl}</div>"
            f"</div>"
        )
        part_html += card

    part_html += "</body></html>"
    part_pdf = os.path.join(temp_dir, f"exam_{idx}.pdf")
    print(f"[{idx}/{len(exams_order)}] Rendering {m['name']} ({len(qs)} Qs)...")
    success = render_html_to_pdf(part_html, part_pdf)
    if success:
        pdf_parts.append(part_pdf)
    else:
        print(f"Warning: failed to render {part_pdf}")

# 3. Merge all parts into final PDF using pymupdf
print(f"\nMerging {len(pdf_parts)} PDF documents...")
master_doc = pymupdf.open()
for part in pdf_parts:
    if os.path.exists(part):
        doc = pymupdf.open(part)
        master_doc.insert_pdf(doc)
        doc.close()

master_doc.save(pdf_final_path)
page_count = len(master_doc)
master_doc.close()

size = os.path.getsize(pdf_final_path)
print(f"\n==========================================")
print(f"SUCCESS: Generated final PDF!")
print(f"File: {pdf_final_path}")
print(f"Total Pages: {page_count}")
print(f"File Size: {size:,} bytes ({size / (1024*1024):.2f} MB)")
print(f"==========================================")
