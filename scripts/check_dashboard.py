# -*- coding: utf-8 -*-
"""Acceptance checks (spec section 6). Run after build_dashboard_data.py."""
import hashlib
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, 'public', 'data')


def load(p):
    with io.open(os.path.join(D, p), encoding='utf-8') as f:
        return json.load(f)


ok = []
nat = load('national.json')
assert nat['n_schools'] == 24648, nat
ok.append(f"national n_schools={nat['n_schools']}")
ok.append(f"coverage_1405={nat['coverage_1405']} warning={nat['coverage_1405_warning']}")

prov = load('by-province.json')
assert sum(r['n_schools'] for r in prov) == 24648
assert len(prov) == 32
ok.append(f"by-province sum={sum(r['n_schools'] for r in prov)} over {len(prov)} provinces")

g = load('graph/full.json')
assert g['meta']['n_schools'] == 24648 and len(g['schools']) == 24648
assert len(g['districts']) == 558
ok.append(f"graph schools={len(g['schools'])} districts={len(g['districts'])}")
size_mb = os.path.getsize(os.path.join(D, 'graph', 'full.json')) / 1e6
assert size_mb <= 6, size_mb
ok.append(f"graph size={size_mb:.1f}MB (<=6MB target)")

s = load('search-index.json')
assert len(s) == 24648
ok.append(f"search-index={len(s)}")

import pandas as pd
ids = set(pd.read_parquet(os.path.join(ROOT, 'schools_data.parquet'))['school_id'].astype(str))
assert {x['id'] for x in s} == ids, 'search IDs diverge'
assert {x[0] for x in g['schools']} == ids, 'graph IDs diverge'
ok.append('search+graph school_id sets == dataset (no school added/lost)')

# founder spot-check: 10 largest clusters
rep = os.path.join(ROOT, 'reports', 'founder_clusters.csv')
import csv
with io.open(rep, encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f))
assert all(int(r['n_schools']) >= 2 for r in rows)
ok.append(f"founder report: {len(rows)} multi-school clusters; top={rows[0]['n_schools']}x {rows[0]['founder_display'][:20]}")

# no foreign assets besides the 3 allowed CDNs
allowed = {'cdn.jsdelivr.net', 'echarts', 'fuse', 'vazirmatn', 'rastikerdar'}
import re
ext = set()
for html in ['index.html', 'network/index.html'] + \
           [f'provinces/{p}' for p in os.listdir(os.path.join(ROOT, 'public', 'provinces'))]:
    txt = io.open(os.path.join(ROOT, 'public', html), encoding='utf-8').read()
    # only real asset refs (scripts, stylesheets, fonts), not plain hyperlinks
    for m in re.findall(r'(?:src|href)="https?://([^/"\s]+)[^"]*\.(?:js|css|woff2?)(?:\?[^"]*)?"', txt):
        ext.add(m)
ok.append(f'external hosts in HTML: {sorted(ext)}')
assert all(any(a in h for a in ('jsdelivr',)) for h in ext), ext

h1 = hashlib.sha256(io.open(os.path.join(D, 'graph', 'full.json'), 'rb').read()).hexdigest()[:16]
ok.append(f'full.json sha={h1} (compare across runs for byte-identical)')

print('\n'.join('PASS: ' + x for x in ok))
