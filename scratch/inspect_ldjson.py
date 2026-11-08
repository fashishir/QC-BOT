import json
from bs4 import BeautifulSoup

with open('data/raw_html/sattacademy/exam_6388_c9ec140235121a08.html', 'r', encoding='utf-8', errors='ignore') as f:
    soup = BeautifulSoup(f.read(), 'lxml')

for s in soup.find_all('script', type='application/ld+json'):
    try:
        data = json.loads(s.string)
        print("LD+JSON type:", data.get('@type'))
        if data.get('@type') == 'FAQPage':
            entities = data.get('mainEntity', [])
            print(f"Entities count: {len(entities)}")
            if entities:
                print("Sample entity:", entities[0])
    except Exception as e:
        print("err:", e)
