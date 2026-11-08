import glob
import os
from bs4 import BeautifulSoup

satta_files = glob.glob('data/raw_html/sattacademy/exam_*.html')
print(f"Found {len(satta_files)} SattAcademy exam files")

has_expl = 0
for sf in satta_files[:5]:
    with open(sf, 'r', encoding='utf-8', errors='ignore') as f:
        html = f.read()
    soup = BeautifulSoup(html, 'lxml')
    # Look for explanation classes or texts
    expls = soup.select('.explanation, .explain, .ans-explanation, [class*="expl"]')
    print(f"{os.path.basename(sf)}: found {len(expls)} expl elements")
    if 'ব্যাখ্যা' in html:
        print(f"  'ব্যাখ্যা' appeared in {os.path.basename(sf)}")
