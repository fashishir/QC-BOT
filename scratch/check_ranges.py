import csv

with open('2025_2026_Job_Exam_MCQ_2000_With_Explanation.csv', mode='r', encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f))

current_exam = None
start_no = 0
exam_ranges = []

for idx, r in enumerate(rows):
    ename = r['exam_name']
    sno = int(r['serial_no'])
    if ename != current_exam:
        if current_exam is not None:
            exam_ranges.append((current_exam, start_no, sno - 1, (sno - start_no)))
        current_exam = ename
        start_no = sno

exam_ranges.append((current_exam, start_no, int(rows[-1]['serial_no']), (int(rows[-1]['serial_no']) - start_no + 1)))

for ename, s, e, cnt in exam_ranges:
    print(f"{s:4d} - {e:4d} ({cnt:3d} qs): {ename}")
