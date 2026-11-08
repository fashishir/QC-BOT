import csv

with open('2025_2026_Job_Exam_MCQ_2000_With_Explanation.csv', mode='r', encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f))

missing_correct_opt = 0
missing_correct_ans = 0
missing_options = 0
promo_count = 0

for idx, r in enumerate(rows):
    if not r.get('correct_option') or r.get('correct_option').strip() not in ['ক', 'খ', 'গ', 'ঘ']:
        missing_correct_opt += 1
    if not r.get('correct_answer_text') or not r.get('correct_answer_text').strip():
        missing_correct_ans += 1
    if not r.get('option_1') or not r.get('option_2') or not r.get('option_3') or not r.get('option_4'):
        missing_options += 1
    expl = r.get('explanation', '')
    if 'অ্যাপ ইনস্টল করুন' in expl or 'অথেনটিক ব্যাখ্যা' in expl or 'Live MCQ' in expl and len(expl) < 150:
        promo_count += 1

print(f"Total rows: {len(rows)}")
print(f"Missing/invalid correct_option: {missing_correct_opt}")
print(f"Missing correct_answer_text: {missing_correct_ans}")
print(f"Missing any option_1..4: {missing_options}")
print(f"Promo explanations count: {promo_count}")
