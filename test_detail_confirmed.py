# -*- coding: utf-8 -*-
import json
from scraper import get_schools, get_school_detail, get_school_licenses

found = None
for gender in ['1', '2']:
    page = 1
    while True:
        try:
            r = get_schools('IR2O2O8O3', gender=gender, page=page, limit=50)
        except Exception:
            break
        items = r.get('items', [])
        if not items:
            break
        for s in items:
            if s.get('confirmTution') or (s.get('tution') and s['tution'] != 'در انتظار تایید'):
                found = s
                break
        if found:
            break
        page += 1
    if found:
        break

out = {'found': found}
if found:
    sp = found['school_path']
    out['detail'] = get_school_detail(sp)
    out['licenses'] = get_school_licenses(sp)

    # also tuition history endpoint directly
    from scraper import make_request, MY_PORTAL_URL, HEADERS_MY_PORTAL, PORTAL_KEY
    payload = {
        'serviceId': 'my.mosharekatha.ir',
        'key': 'my-mosharekatha/school-panel/school-tuition-history/load',
        'params': {'school_path': sp}
    }
    out['tuition_history'] = make_request(MY_PORTAL_URL, payload, HEADERS_MY_PORTAL, PORTAL_KEY)

with open('test_detail_confirmed.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print('OK, found:', bool(found))
