import sys
import io
import requests
from bs4 import BeautifulSoup

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

url = "https://sattacademy.com/board-exams/social-work-2nd-paper-hsc-combined-boardall-2026/mcq"
r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
soup = BeautifulSoup(r.text, "lxml")

cards = [c for c in soup.select("div.card") if c.select_one("span.question-span")]
print(f"Total question cards on page 1: {len(cards)}")

if cards:
    c0 = cards[0]
    stem_el = c0.select_one("span.question-span")
    print("Question 1 Stem:", stem_el.text.strip() if stem_el else "None")
    
    labels = c0.select(".reading-mode-data label") or c0.select("label")
    print(f"Options count: {len(labels)}")
    for idx, lbl in enumerate(labels, 1):
        print(f"  Opt {idx}: {lbl.text.strip()}")
        
    ans_inp = c0.select_one('input[name="answer"]')
    print("Answer input:", ans_inp.get("value") if ans_inp else "None")
    
    check_icon = c0.select(".fa-check-circle")
    print("fa-check-circle count:", len(check_icon))
    if check_icon:
        print("fa-check-circle parent:", check_icon[0].find_parent("label") or check_icon[0].find_parent())
