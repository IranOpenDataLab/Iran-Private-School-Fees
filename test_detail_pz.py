# -*- coding: utf-8 -*-
import json
from scraper import (get_school_detail, get_school_licenses,
                     make_request, MY_PORTAL_URL, HEADERS_MY_PORTAL, PORTAL_KEY)

sp = 'IR2O2O8O3Opz'
out = {}
out['detail'] = get_school_detail(sp)
out['licenses'] = get_school_licenses(sp)

payload = {
    'serviceId': 'my.mosharekatha.ir',
    'key': 'my-mosharekatha/school-panel/school-tuition-history/load',
    'params': {'school_path': sp}
}
out['tuition_history'] = make_request(MY_PORTAL_URL, payload, HEADERS_MY_PORTAL, PORTAL_KEY)

with open('test_detail_pz.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print('OK')
