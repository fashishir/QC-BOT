from bs4 import BeautifulSoup
import re

with open('data/raw_html/sattacademy/exam_6388_c9ec140235121a08.html', 'r', encoding='utf-8', errors='ignore') as f:
    soup = BeautifulSoup(f.read(), 'lxml')

for node in soup.find_all(text=re.compile(r'ব্যাখ্যা')):
    parent = node.parent
    print(f"Parent tag: {parent.name}, class: {parent.get('class')}, text snippet: {parent.get_text()[:100]}")
    break
