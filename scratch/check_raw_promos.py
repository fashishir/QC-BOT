from bs4 import BeautifulSoup
import glob
import os

files = glob.glob('data/raw_html/livemcq/*.html')
for f in files:
    with open(f, 'r', encoding='utf-8', errors='ignore') as fp:
        txt = fp.read()
    promo_in_f = 'Live MCQ অ্যাপ' in txt or 'অ্যাপ ইন্সটল করুন' in txt or 'অ্যাপ ইনস্টল করুন' in txt
    expl_blocks = txt.count('qc__expl-body')
    print(f"{os.path.basename(f)}: expl_blocks={expl_blocks}, promo={promo_in_f}")
