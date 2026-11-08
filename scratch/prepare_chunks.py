import csv
import json
import os

with open('2025_2026_Job_Exam_MCQ_2000_With_Explanation.csv', mode='r', encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f))

# First fix row 656 if missing options
r656 = rows[655]
if not r656['option_3']:
    r656['option_3'] = '{2, 4}'
if not r656['option_4']:
    r656['option_4'] = '{3, 4, 6}'

to_explain = []
for idx, r in enumerate(rows):
    expl = r.get('explanation', '').strip()
    if 'অ্যাপ ইনস্টল করুন' in expl or 'অ্যাপ ইন্সটল করুন' in expl or 'অথেনটিক ব্যাখ্যা দেখতে' in expl or (len(expl) < 150 and 'Live MCQ' in expl):
        to_explain.append({
            'serial_no': int(r['serial_no']),
            'exam_name': r['exam_name'],
            'question_text': r['question_text'],
            'option_1': r['option_1'],
            'option_2': r['option_2'],
            'option_3': r['option_3'],
            'option_4': r['option_4'],
            'correct_option': r['correct_option'],
            'correct_answer_text': r['correct_answer_text'],
        })

print(f"Total questions needing explanation: {len(to_explain)}")

CHUNK_SIZE = 35
chunks = [to_explain[i:i + CHUNK_SIZE] for i in range(0, len(to_explain), CHUNK_SIZE)]
print(f"Total chunks ({CHUNK_SIZE} per chunk): {len(chunks)}")

for c_idx, chunk in enumerate(chunks, 1):
    chunk_file = f"scratch/chunk_{c_idx:02d}.json"
    with open(chunk_file, 'w', encoding='utf-8') as f:
        json.dump(chunk, f, ensure_ascii=False, indent=2)

print(f"Saved {len(chunks)} chunk files in scratch/")
