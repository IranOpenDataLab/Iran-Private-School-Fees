# -*- coding: utf-8 -*-
import json
import time
from scraper import get_provinces, get_districts, get_schools, get_school_detail, get_school_licenses

out = {}

# 1. Provinces
provs = get_provinces()
out['provinces_count'] = len(provs)
out['provinces_sample'] = [(p['title'], p['key']) for p in provs[:3]]

# 2. Districts for Tehran city
dists = get_districts('IR2O2O8')
out['tehran_districts_count'] = len(dists)

# 3. Pagination tests on district IR2O2O8O3 (Tehran region 1)
r1 = get_schools('IR2O2O8O3', gender='1', page=1, page_size=50)
out['page1_items'] = len(r1.get('items', []))
out['page1_total'] = r1.get('totalCount')
out['page1_first'] = r1['items'][0]['school_name'] if r1.get('items') else None

r2 = get_schools('IR2O2O8O3', gender='1', page=2, page_size=50)
out['page2_items'] = len(r2.get('items', []))
out['page2_first'] = r2['items'][0]['school_name'] if r2.get('items') else None
out['page2_last'] = r2['items'][-1]['school_name'] if r2.get('items') else None

# overlap check between page1 and page2
p1_paths = [s['school_path'] for s in r1.get('items', [])]
p2_paths = [s['school_path'] for s in r2.get('items', [])]
out['overlap_p1_p2'] = len(set(p1_paths) & set(p2_paths))

# last page
r6 = get_schools('IR2O2O8O3', gender='1', page=6, page_size=50)
out['page6_items'] = len(r6.get('items', []))
r7 = get_schools('IR2O2O8O3', gender='1', page=7, page_size=50)
out['page7_items'] = len(r7.get('items', []))
out['page7_raw_keys'] = list(r7.keys())

# 4. Find a school with confirmed tuition and fetch its detail
target = None
for s in r1.get('items', []):
    if s.get('confirmTution'):
        target = s
        break
if not target:
    # scan more pages
    for pg in range(2, 7):
        rr = get_schools('IR2O2O8O3', gender='1', page=pg, page_size=50)
        for s in rr.get('items', []):
            if s.get('confirmTution'):
                target = s
                break
        if target:
            break
out['confirmed_school'] = target

# detail on first school regardless
first = r1['items'][0] if r1.get('items') else None
if first:
    d = get_school_detail(first['school_path'])
    out['detail_first'] = d
    l = get_school_licenses(first['school_path'])
    out['licenses_first'] = l

if target:
    d2 = get_school_detail(target['school_path'])
    out['detail_confirmed'] = d2
    l2 = get_school_licenses(target['school_path'])
    out['licenses_confirmed'] = l2

# 5. gender=2 sample
g2 = get_schools('IR2O2O8O3', gender='2', page=1, page_size=50)
out['girls_page1'] = len(g2.get('items', []))
out['girls_total'] = g2.get('totalCount')

with open('test_out.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print("OK, wrote test_out.json")
