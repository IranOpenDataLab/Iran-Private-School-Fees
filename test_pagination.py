# -*- coding: utf-8 -*-
import json
from scraper import get_schools

out = {}
p1 = get_schools('IR2O2O8O3', gender='1', page=1, limit=50)
p2 = get_schools('IR2O2O8O3', gender='1', page=2, limit=50)
out['total'] = p1.get('totalCount')
out['p1_count'] = len(p1.get('items', []))
out['p2_count'] = len(p2.get('items', []))
out['p1_first'] = p1['items'][0]['school_name'] if p1.get('items') else None
out['p2_first'] = p2['items'][0]['school_name'] if p2.get('items') else None
s1 = {s['school_path'] for s in p1.get('items', [])}
s2 = {s['school_path'] for s in p2.get('items', [])}
out['overlap'] = len(s1 & s2)

# last pages
total = int(p1.get('totalCount') or 0)
last_page = (total + 49) // 50 if total else 0
pL = get_schools('IR2O2O8O3', gender='1', page=last_page, limit=50)
out['last_page'] = last_page
out['last_count'] = len(pL.get('items', []))
try:
    pE = get_schools('IR2O2O8O3', gender='1', page=last_page + 1, limit=50)
    out['after_last_count'] = len(pE.get('items', []))
except Exception as e:
    out['after_last_error'] = str(e)

with open('test_pagination.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print('OK')
