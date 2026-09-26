# -*- coding: utf-8 -*-
"""Acceptance checks (spec section 6). Run after build_dashboard_data.py."""
import csv
import hashlib
import io
import json
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, 'docs', 'data')


def load(p):
    with io.open(os.path.join(D, p), encoding='utf-8') as f:
        return json.load(f)


ok = []
nat = load('national.json')
assert nat['n_schools'] == 24648, nat
ok.append(f"national n_schools={nat['n_schools']}")
ok.append(f"n_with_1405={nat['n_with_1405']} quarantined={len(nat['quarantined'])}")
assert nat.get('unit') == 'تومان', nat.get('unit')
ok.append(f"money unit=Toman, below-minimum={nat.get('n_below_minimum')}")

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

s1405 = load('schools-1405.json')
assert s1405['n'] == len(s1405['schools']) == nat['n_with_1405']
ok.append(f"schools-1405={s1405['n']}")

ext = load('extremes.json')
assert len(ext) == 6 and all(r['max_rest'] for r in ext)
ok.append(f"extremes: {len(ext)} stages, all have max_rest (outlier quarantined)")

import pandas as pd
ids = set(pd.read_parquet(os.path.join(ROOT, 'schools_data.parquet'))['school_id'].astype(str))
assert {x['id'] for x in s} == ids, 'search IDs diverge'
assert {x[0] for x in g['schools']} == ids, 'graph IDs diverge'
ok.append('search+graph school_id sets == dataset (no school added/lost)')

with io.open(os.path.join(ROOT, 'reports', 'founder_clusters.csv'),
             encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f))
assert all(int(r['n_schools']) >= 2 for r in rows)
ok.append(f"founder report: {len(rows)} multi-school clusters")

# district pages: 558 generated
dpages = os.listdir(os.path.join(ROOT, 'docs', 'districts'))
assert len(dpages) == 558, len(dpages)
ok.append(f"district pages={len(dpages)}")

# no foreign assets besides the allowed CDN
ext_hosts = set()
pages = ['index.html', 'network/index.html']
pages += [f'provinces/{p}' for p in os.listdir(os.path.join(ROOT, 'docs', 'provinces'))]
pages += [f'districts/{p}' for p in dpages[:20]]
for html in pages:
    txt = io.open(os.path.join(ROOT, 'docs', html), encoding='utf-8').read()
    for m in re.findall(r'(?:src|href)="https?://([^/"\s]+)[^"]*\.(?:js|css|woff2?)(?:\?[^"]*)?"', txt):
        ext_hosts.add(m)
ok.append(f'external asset hosts: {sorted(ext_hosts)}')
assert ext_hosts <= {'cdn.jsdelivr.net', 'unpkg.com'}, ext_hosts

# methodology page ships with the site
assert os.path.exists(os.path.join(ROOT, 'docs', 'methodology.html'))
ok.append('methodology.html present')

h1 = hashlib.sha256(io.open(os.path.join(D, 'graph', 'full.json'), 'rb').read()).hexdigest()[:16]
ok.append(f'full.json sha={h1} (compare across runs for byte-identical)')

print('\n'.join('PASS: ' + x for x in ok))
