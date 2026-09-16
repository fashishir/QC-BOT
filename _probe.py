"""Probe: can PyMuPDF Story render shaped Bengali? (temporary)"""
import glob
import os
import shutil
import sys

import fitz

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

cands = []
for pat in ("C:/Windows/Fonts/*.ttf", "C:/Windows/Fonts/*.ttc"):
    cands += glob.glob(pat)
bn = [p for p in cands if any(k in os.path.basename(p).lower()
                              for k in ("nirmala", "vrinda", "shruti", "noto", "bangla"))]
print("bengali fonts found:", bn)

font = bn[0]
os.makedirs("_probe_fonts", exist_ok=True)
shutil.copy(font, os.path.join("_probe_fonts", "bn.ttf"))
arch = fitz.Archive("_probe_fonts")

HTML = """<html><body>
<h1>বাংলাদেশ ও বিশ্বপরিচয়</h1>
<p>টাইটান কোন গ্রহের উপগ্রহ?</p>
<p>সংস্কৃতি, বিজ্ঞান, শিক্ষা, ক্ষুদ্র, উজ্জ্বল, দ্বন্দ্ব, পূর্ণ, বুদ্ধি</p>
<div>(ক) শনি (খ) বৃহস্পতি (গ) নেপচুন (ঘ) ইউরেনাস</div>
</body></html>"""

css = "@font-face {font-family: bn; src: url(bn.ttf);} body {font-family: bn; font-size: 13pt;}"

story = fitz.Story(html=HTML, user_css=css, archive=arch)
writer = fitz.DocumentWriter("_probe.pdf")
mediabox = fitz.paper_rect("a4")
where = mediabox + (36, 36, -36, -36)
pages = 0
while True:
    dev = writer.begin_page(mediabox)
    more, filled = story.place(where)
    story.draw(dev)
    writer.end_page()
    pages += 1
    if not more or pages > 4:
        break
writer.close()
print("pages:", pages)

doc = fitz.open("_probe.pdf")
txt = doc[0].get_text()
print("--- extracted text (round-trips only if font was embedded+loaded) ---")
print(repr(txt[:220]))
doc[0].get_pixmap(dpi=130).save("_probe.png")
print("saved _probe.png")
doc.close()