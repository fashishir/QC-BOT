import csv
from collections import defaultdict

with open('2025_2026_Job_Exam_MCQ_2000_With_Explanation.csv', mode='r', encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f))

exams = defaultdict(lambda: {'total': 0, 'promo': 0, 'source': set()})
for r in rows:
    ename = r.get('exam_name', '')
    expl = r.get('explanation', '')
    exams[ename]['total'] += 1
    exams[ename]['source'].add(r.get('source_url', ''))
    if 'অ্যাপ ইনস্টল করুন' in expl or 'অথেনটিক ব্যাখ্যা দেখতে' in expl:
        exams[ename]['promo'] += 1

print(f"Total rows: {len(rows)}")
for name, data in exams.items():
    src = list(data['source'])[0] if data['source'] else ''
    print(f"{name} | {data['promo']}/{data['total']} promo | {src}")
