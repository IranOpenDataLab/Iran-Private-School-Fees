# -*- coding: utf-8 -*-
"""
Build static-dashboard data exports from the immutable dataset.

Input : schools_data.parquet (45 columns, 24,648 rows) -- NEVER modified.
Output: public/data/**  +  public/provinces/*.html  +  public/sitemap.xml
        reports/founder_clusters.csv   (human-reviewable founder clusters)

Additive export layer (dataset is read-only input).
  * additive only; fail-fast on missing columns (no partial output);
  * base year for ranking/sizing/links = 1404 (spec appendix B);
  * NO school is dropped from any output -- filters are display-only;
  * offline deterministic layout with fixed SEED (byte-identical re-runs);
  * counts asserted: 24,648 schools everywhere.

Usage:  python build_dashboard_data.py
Requires: pandas, pyarrow (see dashboard-requirements.txt)
"""
import csv
import hashlib
import io
import json
import math
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ROOT = os.path.dirname(os.path.abspath(__file__))
PARQUET = os.path.join(ROOT, 'schools_data.parquet')
DOCS = os.path.join(ROOT, 'docs')          # GitHub Pages source (/docs on main)
DATA = os.path.join(DOCS, 'data')
REPORTS = os.path.join(ROOT, 'reports')
LIVE_URL = 'https://iranopendatalab.github.io/Iran-Private-School-Fees'

EXPECTED_SCHOOLS = 24648
BASE_YEAR = 1404
YEARS = (1403, 1404, 1405)
SEED = 1405  # recorded for audit; layout itself is fully deterministic (no RNG)

# Outlier quarantine (display/ranking only; dataset untouched): money values
# above this cap are implausible (max sane total in dataset ~= 2.7e9 Rial)
# and are treated as missing. Every case is listed in national.json.
MONEY_CAP = 50_000_000_000

# «تهران» for the extremes table = both Tehran records.
TEHRAN = {'شهر تهران', 'شهرستان های تهران'}

REQUIRED_COLUMNS = {
    'province', 'district', 'school_name', 'school_id', 'school_path',
    'school_url', 'gender', 'stage', 'address', 'manager', 'founder',
    'license_holder', 'licenses_count', 'confirm_tuition',
    'process_status', 'process_status_label',
    '1403_tuition', '1403_extra_curricular', '1403_total',
    '1404_tuition', '1404_extra_curricular', '1404_total',
    '1405_tuition', '1405_extra_curricular', '1405_total',
    '1405_final_tuition',
}

# ---------------------------------------------------------------- slugs ---

PROVINCE_SLUGS = {
    'آذربایجان شرقی': 'east-azerbaijan',
    'آذربایجان غربی': 'west-azerbaijan',
    'اردبیل': 'ardabil',
    'اصفهان': 'isfahan',
    'البرز': 'alborz',
    'ایلام': 'ilam',
    'بوشهر': 'bushehr',
    'خراسان جنوبی': 'south-khorasan',
    'خراسان رضوی': 'razavi-khorasan',
    'خراسان شمالی': 'north-khorasan',
    'خوزستان': 'khuzestan',
    'زنجان': 'zanjan',
    'سمنان': 'semnan',
    'سیستان وبلوچستان': 'sistan-baluchestan',
    'شهر تهران': 'tehran-city',
    'شهرستان های تهران': 'tehran-province',
    'فارس': 'fars',
    'قزوین': 'qazvin',
    'قم': 'qom',
    'لرستان': 'lorestan',
    'مازندران': 'mazandaran',
    'مرکزی': 'markazi',
    'هرمزگان': 'hormozgan',
    'همدان': 'hamedan',
    'چهارمحال وبختیاری': 'chaharmahal-bakhtiari',
    'کردستان': 'kurdistan',
    'کرمان': 'kerman',
    'کرمانشاه': 'kermanshah',
    'کهکیلویه وبویراحمد': 'kohgiluyeh-boyerahmad',
    'گلستان': 'golestan',
    'گیلان': 'gilan',
    'یزد': 'yazd',
}

# ------------------------------------------------------- normalization ---

_AR_FA = str.maketrans({'ي': 'ی', 'ك': 'ک', 'ة': 'ه', 'ؤ': 'و', 'إ': 'ا', 'أ': 'ا', 'آ': 'ا'})
_FA_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
_PUNCT_RE = re.compile(r'[‐‑‒–—ـ_\"\'«»\(\)\[\]\{\}\.,:;،؛؟!\*\+=~\/\\|<>`^#@&×÷]')
_WS_RE = re.compile(r'\s+')

FOUNDER_DROP_WORDS = {
    'موسسه', 'موسس', 'اموزش', 'اموزشی', 'فرهنگ', 'فرهنگی', 'غیرانتفاعی',
    'تعاون', 'تعاونی', 'مجتمع', 'مدرسه', 'دبیرستان', 'دبستان', 'هنرستان',
    'پسرانه', 'دخترانه', 'خاص', 'نمونه', 'هیات', 'امن', 'عام', 'خاصه',
}
SCHOOL_DROP_WORDS = {
    'دبیرستان', 'دبستان', 'هنرستان', 'مجتمع', 'اموزش', 'اموزشی', 'مدرسه',
    'پسرانه', 'دخترانه', 'متوسطه', 'ابتدایی', 'استثنایی',
}


def unify_yzk(s):
    """Unify Arabic/FA y/k/h + FA digits; collapse whitespace."""
    s = (s or '').translate(_AR_FA).translate(_FA_DIGITS)
    s = _PUNCT_RE.sub(' ', s)
    return _WS_RE.sub(' ', s).strip()


def norm_founder(raw):
    """Normalized founder name for clustering (-> founder_hash input)."""
    s = unify_yzk(raw)
    words = [w for w in s.split(' ') if w and w not in FOUNDER_DROP_WORDS]
    s = ' '.join(words)
    s = re.sub(r'\d+', '', s)  # device/branch numbers are not identity
    return _WS_RE.sub(' ', s).strip()


def norm_school_name(raw):
    """Normalized school name for the same-name edge rule."""
    s = unify_yzk(raw)
    words = [w for w in s.split(' ') if w and w not in SCHOOL_DROP_WORDS]
    s = ' '.join(words)
    s = re.sub(r'\d+$', '', s).strip()  # trailing branch numbers
    return _WS_RE.sub(' ', s).strip()


def short_hash(s):
    return hashlib.sha1(s.encode('utf-8')).hexdigest()[:8]


# ------------------------------------------------------------- helpers ---

def fail(msg):
    print(f'BUILD-ERROR: {msg}')
    sys.exit(1)


def parse_money(v):
    """Dataset money strings -> int Rial, or None when empty/textual."""
    if v is None:
        return None
    if isinstance(v, float):
        if math.isnan(v):
            return None
        return int(round(v))
    s = str(v).strip().replace(',', '').replace('٬', '').replace('٫', '').replace(' ', '')
    if not s:
        return None
    try:
        return int(round(float(s)))
    except ValueError:
        return None


def quantiles(vals):
    """[q1, median, q3] of a non-empty int list (linear interpolation)."""
    s = sorted(vals)
    n = len(s)
    if n == 0:
        return [None, None, None]
    if n == 1:
        return [s[0], s[0], s[0]]

    def q(p):
        k = (n - 1) * p
        f = math.floor(k)
        c = math.ceil(k)
        return s[f] if f == c else s[f] + (s[c] - s[f]) * (k - f)

    return [q(0.25), q(0.5), q(0.75)]


def mean(vals):
    return (sum(vals) / len(vals)) if vals else None


def r1(x):
    return None if x is None else round(x, 1)


def dump_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(obj, f, ensure_ascii=False, separators=(',', ':'))
        f.write('\n')


def dataset_updated():
    """Dual-date stamp from the last commit touching the parquet (else mtime)."""
    try:
        out = subprocess.run(
            ['git', 'log', '-1', '--format=%cI', '--', 'schools_data.parquet'],
            cwd=ROOT, capture_output=True, text=True, timeout=30)
        ts = out.stdout.strip()
        if ts:
            return datetime.fromisoformat(ts).strftime('%Y-%m-%d %H:%M')
    except Exception:
        pass
    return datetime.fromtimestamp(
        os.path.getmtime(PARQUET), tz=timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M')


# ----------------------------------------------------------------- main ---

def main():
    import pandas as pd

    if not os.path.exists(PARQUET):
        fail('schools_data.parquet not found')
    df = pd.read_parquet(PARQUET)

    missing = sorted(REQUIRED_COLUMNS - set(df.columns))
    if missing:
        fail(f'missing columns in dataset: {missing} -- refusing partial output')

    n = len(df)
    if n != EXPECTED_SCHOOLS:
        fail(f'row count {n} != expected {EXPECTED_SCHOOLS}')
    print(f'rows: {n} (expected {EXPECTED_SCHOOLS}) -- ok')

    S = lambda c: df[c].fillna('').astype(str)  # noqa: E731
    province = S('province')
    district = S('district')
    school_name = S('school_name')
    school_id = S('school_id').str.strip()
    school_path = S('school_path').str.strip()
    school_url = S('school_url').str.strip()
    gender = S('gender').str.strip()
    stage = S('stage').str.strip()
    founder_raw = S('founder')

    if school_id.str.len().eq(0).any():
        fail('blank school_id found')
    if (~school_id.duplicated(keep=False)).sum() != n and school_id.duplicated().any():
        dupes = school_id[school_id.duplicated()].unique().tolist()[:5]
        fail(f'duplicate school_id values: {dupes}')

    # ---- province slugs (fail-fast: unknown province -> FA fallback + warning)
    provinces = sorted(province.unique().tolist())
    slugs = {}
    for p in provinces:
        slug = PROVINCE_SLUGS.get(p)
        if slug is None:
            print(f'WARNING: no slug mapping for province {p!r} -- using FA fallback')
            slug = p
        slugs[p] = slug
    dump_json(os.path.join(DATA, 'province_slugs.json'),
              {p: slugs[p] for p in provinces})

    # ---- money vectors (sanitized: outlier quarantine, dataset untouched)
    tot = {y: [parse_money(v) for v in df[f'{y}_total']] for y in YEARS}
    tui = {y: [parse_money(v) for v in df[f'{y}_tuition']] for y in YEARS}
    ext = {y: [parse_money(v) for v in df[f'{y}_extra_curricular']] for y in YEARS}
    quarantined = []
    for y in YEARS:
        for fld, arr in (('total', tot[y]), ('tuition', tui[y]), ('extra', ext[y])):
            for i, v in enumerate(arr):
                if v is not None and v > MONEY_CAP:
                    quarantined.append({'school_id': school_id[i], 'year': y,
                                        'field': fld, 'value': v})
                    arr[i] = None
    if quarantined:
        print(f'WARNING: quarantined {len(quarantined)} implausible money values '
              f'(>{MONEY_CAP}); listed in national.json')

    # ---- display-year values: 1405 when available, else 1404 (+ year tag)
    disp_t, disp_tu, disp_ex, disp_y = [], [], [], []
    for i in range(n):
        if tot[1405][i] is not None:
            disp_t.append(tot[1405][i])
            disp_tu.append(tui[1405][i])
            disp_ex.append(ext[1405][i])
            disp_y.append(1405)
        elif tot[BASE_YEAR][i] is not None:
            disp_t.append(tot[BASE_YEAR][i])
            disp_tu.append(tui[BASE_YEAR][i])
            disp_ex.append(ext[BASE_YEAR][i])
            disp_y.append(1404)
        else:
            disp_t.append(None)
            disp_tu.append(None)
            disp_ex.append(None)
            disp_y.append(None)

    # ---- founder normalization + clustering
    founder_norm = [norm_founder(v) for v in founder_raw]
    founder_hash = [short_hash(v) for v in founder_norm]
    founder_display = {}
    for h, disp in zip(founder_hash, founder_raw):
        d = disp.strip() or 'نامشخص'
        if h not in founder_display:
            founder_display[h] = d
    empty_hash = short_hash('')
    founder_display[empty_hash] = 'نامشخص'

    # ---- district hubs: (province, district) pairs, sorted -> idx
    pairs = sorted(set(zip(province, district)))
    hub_idx = {pair: i for i, pair in enumerate(pairs)}
    hub_of = [hub_idx[(province[i], district[i])] for i in range(n)]
    n_hubs = len(pairs)

    # ---- deterministic offline layout (circular-per-province + rings)
    R_BIG = 1000.0
    prov_list = provinces  # already sorted
    prov_angle = {p: 2 * math.pi * i / len(prov_list) for i, p in enumerate(prov_list)}
    hubs_by_prov = {}
    for i, (p, d) in enumerate(pairs):
        hubs_by_prov.setdefault(p, []).append(i)
    hub_xy = [None] * n_hubs
    for p, idxs in hubs_by_prov.items():
        cx = R_BIG * math.cos(prov_angle[p])
        cy = R_BIG * math.sin(prov_angle[p])
        k = len(idxs)
        rp = 60.0 + 8.0 * math.sqrt(k)
        for j, hi in enumerate(idxs):
            a = 2 * math.pi * j / k
            hub_xy[hi] = (round(cx + rp * math.cos(a), 2),
                          round(cy + rp * math.sin(a), 2))
    # founder centroids (mean hub position of member schools)
    fsum = {}
    for i in range(n):
        h = founder_hash[i]
        x, y = hub_xy[hub_of[i]]
        if h in fsum:
            fsum[h][0] += x
            fsum[h][1] += y
            fsum[h][2] += 1
        else:
            fsum[h] = [x, y, 1]
    fcent = {h: (v[0] / v[2], v[1] / v[2]) for h, v in fsum.items()}
    # schools on golden-angle spiral around own hub, pulled 25% to founder centroid
    GOLDEN = 2.399963
    members = {}
    for i in range(n):
        members.setdefault(hub_of[i], []).append(i)
    sch_xy = [None] * n
    for hi, idxs in members.items():
        idxs.sort(key=lambda i: school_id[i])
        hx, hy = hub_xy[hi]
        for pos, i in enumerate(idxs):
            r = 6.0 * math.sqrt(pos + 1)
            a = pos * GOLDEN
            rx, ry = hx + r * math.cos(a), hy + r * math.sin(a)
            cx, cy = fcent[founder_hash[i]]
            sch_xy[i] = (round(0.75 * rx + 0.25 * cx, 2),
                         round(0.75 * ry + 0.25 * cy, 2))

    # ---- stage / gender indices (sorted -> deterministic)
    stages = sorted(stage.unique().tolist())
    stage_idx = {s: i for i, s in enumerate(stages)}
    genders = sorted(gender.unique().tolist())
    gender_idx = {g: i for i, g in enumerate(genders)}

    # ============================================================ outputs
    updated = dataset_updated()

    # ---- national.json (display-year aggregates: 1405 first, 1404 fallback)
    disp_vals = [v for v in disp_t if v is not None]
    bq = quantiles(disp_vals)
    n1405 = sum(1 for v in tot[1405] if v is not None)
    national = {
        'n_schools': n,
        'n_provinces': len(provinces),
        'n_districts': n_hubs,
        'base_year': BASE_YEAR,
        'display_rule': '1405_total when available, else 1404_total (year tagged)',
        'median_disp': bq[1],
        'q1_disp': bq[0],
        'q3_disp': bq[2],
        'mean_disp': r1(mean(disp_vals)),
        'n_with_disp': len(disp_vals),
        'n_with_1405': n1405,
        'coverage_1405': round(n1405 / n, 4),
        'coverage_1405_warning': (n1405 / n) < 0.6,
        'quarantined': quarantined,
        'updated': updated,
        'seed': SEED,
    }
    dump_json(os.path.join(DATA, 'national.json'), national)

    # ---- district slugs (stable, per province): {pslug}--{k:02d}
    dist_slug = {}
    for p in provinces:
        names = sorted({d for (pp, d) in pairs if pp == p})
        for k, d in enumerate(names):
            dist_slug[(p, d)] = f'{slugs[p]}--{k:02d}'

    # ---- by-province.json (must sum to 24,648)
    by_province = []
    for p in provinces:
        idxs = [i for i in range(n) if province[i] == p]
        vals = [disp_t[i] for i in idxs if disp_t[i] is not None]
        q = quantiles(vals)
        hubs = sorted({hub_of[i] for i in idxs})
        by_province.append({
            'province': p, 'slug': slugs[p], 'n_schools': len(idxs),
            'n_districts': len(hubs), 'n_with_disp': len(vals),
            'n_with_1405': sum(1 for i in idxs if tot[1405][i] is not None),
            'median_disp': q[1], 'q1_disp': q[0], 'q3_disp': q[2],
            'mean_disp': r1(mean(vals)),
        })
    assert sum(r['n_schools'] for r in by_province) == n, 'province split lost schools'
    dump_json(os.path.join(DATA, 'by-province.json'), by_province)

    # ---- by-stage.json / by-gender.json (display-year)
    def slice_stats(key_series, keys):
        out = []
        for k in keys:
            idxs = [i for i in range(n) if key_series[i] == k]
            vals = [disp_t[i] for i in idxs if disp_t[i] is not None]
            q = quantiles(vals)
            out.append({'key': k, 'n_schools': len(idxs), 'n_with_disp': len(vals),
                        'median_disp': q[1], 'q1_disp': q[0], 'q3_disp': q[2],
                        'mean_disp': r1(mean(vals))})
        return out

    by_stage = slice_stats(stage, stages)
    assert sum(r['n_schools'] for r in by_stage) == n, 'stage split lost schools'
    dump_json(os.path.join(DATA, 'by-stage.json'), by_stage)
    by_gender = slice_stats(gender, genders)
    assert sum(r['n_schools'] for r in by_gender) == n, 'gender split lost schools'
    dump_json(os.path.join(DATA, 'by-gender.json'), by_gender)

    # ---- by-stage-gender.json (gender medians inside each stage)
    sg = []
    for s in stages:
        row = {'stage': s, 'genders': []}
        for g in genders:
            idxs = [i for i in range(n) if stage[i] == s and gender[i] == g]
            vals = [disp_t[i] for i in idxs if disp_t[i] is not None]
            q = quantiles(vals)
            row['genders'].append({'gender': g, 'n': len(idxs),
                                   'median': q[1], 'mean': r1(mean(vals))})
        sg.append(row)
    dump_json(os.path.join(DATA, 'by-stage-gender.json'), sg)

    # ---- timeseries.json
    ts = []
    for y in YEARS:
        vals = [v for v in tot[y] if v is not None]
        tv = [v for v in tui[y] if v is not None]
        ev = [v for v in ext[y] if v is not None]
        q = quantiles(vals)
        ts.append({'year': y, 'n_with_total': len(vals),
                   'median_total': q[1], 'q1_total': q[0], 'q3_total': q[2],
                   'mean_total': r1(mean(vals)),
                   'median_tuition': quantiles(tv)[1], 'median_extra': quantiles(ev)[1]})
    dump_json(os.path.join(DATA, 'timeseries.json'), ts)

    # ---- modal-ready lite entry: full history + display-year (clickable everywhere)
    def entry(i):
        return {'n': school_name[i], 'nn': norm_school_name(school_name[i]).lower(),
                'id': school_id[i], 'ps': slugs[province[i]],
                'd': district[i], 's': stage[i], 'g': gender[i],
                'p': school_path[i],
                'y3': [tot[1403][i], tui[1403][i], ext[1403][i]],
                'y4': [tot[BASE_YEAR][i], tui[BASE_YEAR][i], ext[BASE_YEAR][i]],
                'y5': [tot[1405][i], tui[1405][i], ext[1405][i]],
                'fin': (S('1405_final_tuition')[i].strip() or None),
                'dt': disp_t[i], 'dy': disp_y[i],
                'founder': founder_raw[i].strip() or 'نامشخص'}

    # ---- full profile builder (tops: lite + admin fields)
    def profile(i):
        d = entry(i)
        d.update({'school_name': school_name[i], 'school_id': school_id[i],
                  'school_path': school_path[i], 'school_url': school_url[i],
                  'province': province[i], 'province_slug': slugs[province[i]],
                  'district': district[i], 'stage': stage[i], 'gender': gender[i],
                  'license_holder': S('license_holder')[i],
                  'confirm_tuition': str(df['confirm_tuition'].iloc[i]),
                  'process_status_label': S('process_status_label')[i]})
        return d

    # ranking = priciest first by DISPLAY total (1405 ?? 1404), nulls last
    order_key = lambda i: (disp_t[i] is None,  # noqa: E731
                           -(disp_t[i] or 0), school_id[i])

    # ---- top.json (national 200 priciest, display-year)
    top_national = sorted(range(n), key=order_key)[:200]
    dump_json(os.path.join(DATA, 'top.json'), [profile(i) for i in top_national])

    # ---- timeseries-stage.json (per stage x year, year-native)
    ts_stage = []
    for s in stages:
        idxs = [i for i in range(n) if stage[i] == s]
        pts = []
        for y in YEARS:
            vals = [tot[y][i] for i in idxs if tot[y][i] is not None]
            pts.append({'year': y, 'n': len(vals), 'median': quantiles(vals)[1]})
        ts_stage.append({'stage': s, 'n_schools': len(idxs), 'points': pts})
    dump_json(os.path.join(DATA, 'timeseries-stage.json'), ts_stage)

    # ---- stage-province.json (per stage: provincial medians + min/max schools)
    stage_prov = []
    for s in stages:
        sidx = [i for i in range(n) if stage[i] == s]
        sprows = []
        for p in provinces:
            idxs = [i for i in sidx if province[i] == p]
            if not idxs:
                continue
            vals = [(disp_t[i], i) for i in idxs if disp_t[i] is not None]
            q = quantiles([v for v, _ in vals])
            lo = min(vals)[1] if vals else None
            hi = max(vals)[1] if vals else None
            sprows.append({'province': p, 'slug': slugs[p], 'n': len(idxs),
                           'median': q[1],
                           'min': entry(lo) if lo is not None else None,
                           'max': entry(hi) if hi is not None else None})
        stage_prov.append({'stage': s, 'n_schools': len(sidx), 'provinces': sprows})
    dump_json(os.path.join(DATA, 'stage-province.json'), stage_prov)

    # ---- extremes.json (per stage: cheapest/priciest, rest-of-country vs Tehran)
    extremes = []
    for s in stages:
        sidx = [i for i in range(n) if stage[i] == s and disp_t[i] is not None]
        rest = [(disp_t[i], i) for i in sidx if province[i] not in TEHRAN]
        teh = [(disp_t[i], i) for i in sidx if province[i] in TEHRAN]
        extremes.append({
            'stage': s, 'n': len(sidx),
            'min_rest': entry(min(rest)[1]) if rest else None,
            'max_rest': entry(max(rest)[1]) if rest else None,
            'min_tehran': entry(min(teh)[1]) if teh else None,
            'max_tehran': entry(max(teh)[1]) if teh else None,
        })
    dump_json(os.path.join(DATA, 'extremes.json'), extremes)

    # ---- schools-1405.json (every school with a registered 1405 total)
    idx1405 = sorted([i for i in range(n) if tot[1405][i] is not None],
                     key=lambda i: (-tot[1405][i], school_id[i]))
    dump_json(os.path.join(DATA, 'schools-1405.json'),
              {'n': len(idx1405), 'schools': [entry(i) for i in idx1405]})
    assert len(idx1405) == n1405

    # ---- provinces/{slug}.json + {slug}-top.json (display-year)
    for p in provinces:
        idxs = [i for i in range(n) if province[i] == p]
        hubs = sorted({hub_of[i] for i in idxs}, key=lambda hi: pairs[hi][1])
        dist_rows = []
        for hi in hubs:
            members_hi = [i for i in idxs if hub_of[i] == hi]
            vals = [disp_t[i] for i in members_hi if disp_t[i] is not None]
            q = quantiles(vals)
            dist_rows.append({'district': pairs[hi][1],
                              'slug': dist_slug[pairs[hi]],
                              'n_schools': len(members_hi),
                              'n_with_disp': len(vals), 'median_disp': q[1]})
        dump_json(os.path.join(DATA, 'provinces', f'{slugs[p]}.json'),
                  {'province': p, 'slug': slugs[p], 'n_schools': len(idxs),
                   'n_districts': len(hubs),
                   'n_with_1405': sum(1 for i in idxs if tot[1405][i] is not None),
                   'districts': dist_rows})
        top100 = sorted(idxs, key=order_key)[:100]
        by_dist = {}
        for i in top100:
            by_dist.setdefault(district[i], []).append(school_id[i])
        dump_json(os.path.join(DATA, 'provinces', f'{slugs[p]}-top.json'),
                  {'province': p, 'slug': slugs[p],
                   'top': [profile(i) for i in top100],
                   'by_district': by_dist})

    # ---- search-index.json (ALL schools, history + display-year)
    search = [entry(i) for i in range(n)]
    assert len(search) == n, 'search index lost schools'
    dump_json(os.path.join(DATA, 'search-index.json'), search)

    # ---- graph/full.json (compact parallel arrays + precomputed coords)
    # sizing + tooltip use DISPLAY totals (1405 ?? 1404)
    name_hash = [short_hash(norm_school_name(v)) for v in school_name]
    g_districts = []
    for hi, (p, d) in enumerate(pairs):
        members_hi = members[hi]
        vals = [disp_t[i] for i in members_hi if disp_t[i] is not None]
        q = quantiles(vals)
        x, y = hub_xy[hi]
        g_districts.append([hi, d, slugs[p], x, y, len(members_hi), q[1],
                            dist_slug[(p, d)]])
    g_schools = []
    for i in range(n):
        x, y = sch_xy[i]
        g_schools.append([school_id[i], founder_hash[i], hub_of[i],
                          stage_idx[stage[i]], gender_idx[gender[i]],
                          disp_t[i], disp_tu[i], disp_ex[i], disp_y[i],
                          name_hash[i], school_path[i], x, y])
    assert len(g_schools) == n, 'graph lost schools'
    dump_json(os.path.join(DATA, 'graph', 'full.json'),
              {'meta': {'n_schools': n, 'n_districts': n_hubs,
                        'stages': stages, 'genders': genders,
                        'gender_note': 'index into genders',
                        'display_rule': 'totals are display-year (1405 ?? 1404); '
                                        'dy=null means no total in either year',
                        'school_cols': ['school_id', 'founder_hash', 'district_idx',
                                        'stage_idx', 'gender_idx', 'disp_total',
                                        'disp_tuition', 'disp_extra', 'disp_year',
                                        'name_hash', 'school_path', 'x', 'y'],
                        'district_cols': ['idx', 'name', 'province_slug', 'x', 'y',
                                          'n_schools', 'median_disp', 'slug'],
                        'size_rule': 'school symbolSize = 3 + 25*sqrt(disp_total/max_disp)',
                        'base_year': BASE_YEAR, 'seed': SEED,
                        'updated': updated,
                        'edge_rule': 'district edges via district_idx; '
                                     'founder chains via equal founder_hash; '
                                     'strong edge iff equal nm (normalized-name hash)'},
               'districts': g_districts,
               'schools': g_schools,
               'founders': founder_display})

    # ---- reports/founder_clusters.csv (clusters with >= 2 schools)
    clusters = {}
    for i in range(n):
        h = founder_hash[i]
        c = clusters.setdefault(h, {'display': founder_display[h],
                                    'n': 0, 'provs': set(), 'names': set(),
                                    'samples': []})
        c['n'] += 1
        c['provs'].add(province[i])
        c['names'].add(school_name[i])
        if len(c['samples']) < 3:
            c['samples'].append(school_name[i])
    rows = sorted(((h, c) for h, c in clusters.items() if c['n'] >= 2),
                  key=lambda kv: (-kv[1]['n'], kv[0]))
    os.makedirs(REPORTS, exist_ok=True)
    with io.open(os.path.join(REPORTS, 'founder_clusters.csv'), 'w',
                 encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['founder_hash', 'founder_display', 'n_schools',
                    'n_provinces', 'n_distinct_names', 'sample_names'])
        for h, c in rows:
            w.writerow([h, c['display'], c['n'], len(c['provs']),
                        len(c['names']), ' | '.join(c['samples'])])

    # ---- static province + district pages + sitemap (SEO, §4)
    prov_pages = []
    for p in provinces:
        slug = slugs[p]
        with io.open(os.path.join(DATA, 'provinces', f'{slug}.json'),
                     encoding='utf-8') as f:
            pdata = json.load(f)
        with io.open(os.path.join(DATA, 'provinces', f'{slug}-top.json'),
                     encoding='utf-8') as f:
            ptop = json.load(f)
        html = province_page(p, slug, pdata, ptop)
        out_path = os.path.join(DOCS, 'provinces', f'{slug}.html')
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with io.open(out_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(html)
        prov_pages.append(slug)

    dist_pages = []
    for hi, (p, d) in enumerate(pairs):
        slug = dist_slug[(p, d)]
        ordered = sorted(members[hi], key=order_key)
        dentries = [entry(i) for i in ordered]
        vals = [disp_t[i] for i in ordered if disp_t[i] is not None]
        html = district_page(p, d, slug, slugs[p], dentries,
                             quantiles(vals)[1] if vals else None,
                             sum(1 for i in ordered if tot[1405][i] is not None))
        out_path = os.path.join(DOCS, 'districts', f'{slug}.html')
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with io.open(out_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(html)
        dist_pages.append(slug)

    with io.open(os.path.join(DOCS, '.nojekyll'), 'w', encoding='utf-8') as f:
        f.write('')
    sitemap_urls = (['', 'network/', 'methodology.html'] +
                    [f'provinces/{s}.html' for s in sorted(prov_pages)] +
                    [f'districts/{s}.html' for s in sorted(dist_pages)])
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in sitemap_urls:
        sm.append(f'<url><loc>{LIVE_URL}/{u}</loc></url>')
    sm.append('</urlset>')
    with io.open(os.path.join(DOCS, 'sitemap.xml'), 'w',
                 encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(sm) + '\n')

    # ---- final sanity (acceptance §6: counts)
    assert sum(1 for _ in g_schools) == EXPECTED_SCHOOLS
    print('outputs written:')
    for dirpath, _, files in os.walk(DATA):
        for fn in sorted(files):
            fp = os.path.join(dirpath, fn)
            rel = os.path.relpath(fp, ROOT).replace(os.sep, '/')
            print(f'  {rel}  {os.path.getsize(fp) / 1024:.0f} KB')
    print(f'founder clusters (>=2 schools): {len(rows)}; '
          f'singletons: {len(clusters) - len(rows)}')
    print('ALL SANITY CHECKS PASSED '
          f'(n_schools={n}, hubs={n_hubs}, search={len(search)}, '
          f'graph={len(g_schools)})')


FONT_CSS = ('<link rel="stylesheet" '
            'href="https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/Vazirmatn-font-face.css">')
ECHARTS_JS = ('<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"></script>\n'
              '<script>if(!window.echarts){document.write(\'<script src="'
              'https://unpkg.com/echarts@5.5.1/dist/echarts.min.js"></scr\'+\'ipt>\')}</script>')
FUSE_JS = ('<script src="https://cdn.jsdelivr.net/npm/fuse.js@7.0.0/dist/fuse.min.js"></script>\n'
           '<script>if(!window.Fuse){document.write(\'<script src="'
           'https://unpkg.com/fuse.js@7.0.0/dist/fuse.min.js"></scr\'+\'ipt>\')}</script>')


def nav_html(home):
    """Full top menu; home='' on index, '../' on sub-pages (sticky via CSS)."""
    return (
        f'<nav class="topnav"><div class="navin">'
        f'<a href="{home or "./"}">🏠 خانه</a>'
        f'<a href="{home}network/">🕸️ گراف شبکه</a>'
        f'<a href="{home}#search">🔎 جست‌وجو</a>'
        f'<a href="{home}#top">🏆 گران‌ترین‌ها</a>'
        f'<a href="{home}#y1405">✅ ثبت‌شده‌های ۱۴۰۵</a>'
        f'<a href="{home}#provs">🗺️ استان‌ها</a>'
        f'<a href="{home}methodology.html">📖 روش‌شناسی</a>'
        f'</div></nav>')


def foot_html():
    return (
        f'<footer class="foot">نسخه زنده داشبورد: '
        f'<a href="{LIVE_URL}">{LIVE_URL}</a> · داده: '
        f'<a href="https://github.com/IranOpenDataLab/Iran-Private-School-Fees">'
        f'Iran-Private-School-Fees</a> · '
        f'<a href="https://github.com/IranOpenDataLab/Iran-Private-School-Fees/releases">'
        f'Releases</a></footer>')


def year_tag(y):
    """1405 → no tag; 1404 → tiny year note; None → tiny 'no data' note."""
    if y == 1405:
        return ''
    if y == 1404:
        return ' <small>(۱۴۰۴)</small>'
    return ' <small>(—)</small>'


PROVINCE_PAGE_TMPL = """<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<meta name="description" content="__DESC__">
__FONT__
<link rel="stylesheet" href="../assets/style.css">
__ECHARTS__
<script src="../assets/common.js"></script>
<script type="application/ld+json">__SCHEMA__</script>
</head>
<body>
__NAV__
<header class="top"><h1>__H1__</h1><p class="sub">__SUB__</p></header>
<main>
<section class="cards">__CARDS__</section>
<section><h2>میانه آخرین شهریه ثبت‌شده به تفکیک ناحیه — ریال</h2>
<div class="row" style="margin-bottom:8px"><div>
<button class="ghost" type="button" data-png="chart">⬇ خروجی PNG</button>
<button class="ghost" type="button" data-full="chart">🔍 تمام‌صفحه</button>
</div></div>
<div id="chart" class="chart"></div></section>
<section><h2>نواحی (__NDIST__ ناحیه — برای جزییات هر ناحیه کلیک کنید)</h2><div class="tblwrap"><table><thead><tr><th>ناحیه</th><th>مدارس</th><th>میانه</th></tr></thead><tbody>__DROWS__</tbody></table></div></section>
<section><h2>۱۰ مدرسه گران استان (برای پروفایل کلیک کنید)</h2><div class="tblwrap"><table id="topTbl"><thead><tr><th>#</th><th>مدرسه</th><th>ناحیه</th><th>مقطع</th><th>مجموع</th></tr></thead><tbody>__TROWS__</tbody></table></div></section>
</main>
__FOOT__
<script>__DATAJS__</script>
<script>__CHARTJS__</script>
</body>
</html>
"""

DISTRICT_PAGE_TMPL = """<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<meta name="description" content="__DESC__">
__FONT__
<link rel="stylesheet" href="../assets/style.css">
__ECHARTS__
<script src="../assets/common.js"></script>
</head>
<body>
__NAV__
<header class="top"><h1>__H1__</h1><p class="sub">__SUB__</p></header>
<main>
<section class="cards">__CARDS__</section>
<section><h2>۱۵ مدرسه گران ناحیه — ریال</h2>
<div class="row" style="margin-bottom:8px"><div>
<button class="ghost" type="button" data-png="chart">⬇ خروجی PNG</button>
<button class="ghost" type="button" data-full="chart">🔍 تمام‌صفحه</button>
</div></div>
<div id="chart" class="chart"></div></section>
<section><h2>۲۰ مدرسه گران ناحیه (برای پروفایل کلیک کنید)</h2><div class="tblwrap"><table id="topTbl"><thead><tr><th>#</th><th>مدرسه</th><th>مقطع</th><th>مجموع</th></tr></thead><tbody>__TROWS__</tbody></table></div></section>
<section><h2>همه مدارس ناحیه (__N__ مدرسه — برای پروفایل کلیک کنید)</h2><div class="tblwrap"><table id="allTbl"><thead><tr><th>#</th><th>مدرسه</th><th>مقطع</th><th>جنسیت</th><th>مجموع</th></tr></thead><tbody>__AROWS__</tbody></table></div></section>
</main>
__FOOT__
<script>__DATAJS__</script>
<script>__CHARTJS__</script>
</body>
</html>
"""


def fa_num(x):
    if x is None:
        return '—'
    if isinstance(x, float) and x.is_integer():
        x = int(x)
    s = f'{x:,}'.replace(',', '٬') if isinstance(x, int) else str(round(x, 1))
    return s.translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))


def disp_cell(total, year):
    return f'{fa_num(total)}{year_tag(year)}'


def clickable_rows_js(rows):
    """Embed modal-ready rows + click-to-profile wiring for a table."""
    by_id = {r['id']: r for r in rows}
    js = ('var ROWS=' + json.dumps(by_id, ensure_ascii=False) + ';'
          'document.querySelectorAll("a[data-sid]").forEach(function(a){'
          'a.addEventListener("click",function(ev){ev.preventDefault();'
          'var r=ROWS[a.getAttribute("data-sid")];if(r)DSH.profileModal(r);});});')
    return js


def province_page(p, slug, pdata, ptop):
    top = ptop['top']
    vals = [t['dt'] for t in top if t.get('dt') is not None]
    med = quantiles(vals)[1] if vals else None
    cards = (f'<div class="card"><b>{fa_num(pdata["n_schools"])}</b><span>مدرسه</span></div>'
             f'<div class="card"><b>{fa_num(pdata["n_districts"])}</b><span>ناحیه</span></div>'
             f'<div class="card"><b>{fa_num(med)}</b><span>میانه آخرین شهریه ثبت‌شده (ریال)</span></div>'
             f'<div class="card"><b>{fa_num(pdata.get("n_with_1405", 0))}</b><span>ثبت‌شده ۱۴۰۵</span></div>')
    drows = ''.join(
        f'<tr><td><a href="../districts/{d["slug"]}.html">{d["district"]}</a></td>'
        f'<td>{fa_num(d["n_schools"])}</td><td>{fa_num(d["median_disp"])}</td></tr>'
        for d in pdata['districts'])
    trows = ''.join(
        f'<tr><td>{fa_num(k + 1)}</td>'
        f'<td><a href="#" data-sid="{t["school_id"]}">{t["school_name"]}</a></td>'
        f'<td>{t["district"]}</td><td>{t["stage"]}</td>'
        f'<td>{disp_cell(t.get("dt"), t.get("dy"))}</td></tr>'
        for k, t in enumerate(top[:10]))
    names = [d['district'] for d in pdata['districts']]
    meds = [d['median_disp'] or 0 for d in pdata['districts']]
    datajs = clickable_rows_js(top[:10])
    chartjs = ('var el=document.getElementById("chart");var c=echarts.init(el);'
               'var OPT={textStyle:{fontFamily:"Vazirmatn,Tahoma,sans-serif"},'
               'tooltip:{trigger:"item",valueFormatter:function(v){return DSH.faNum(v)+" ریال"}},'
               'xAxis:{type:"value",axisLabel:{formatter:function(v){return DSH.faNum(v)}}},'
               'yAxis:{type:"category",data:'
               + json.dumps(names, ensure_ascii=False) +
               '},series:[{type:"bar",data:' + json.dumps(meds) +
               ',itemStyle:{color:"#1a7f5a"}}],grid:{containLabel:true}};'
               'c.setOption(OPT);DSH.registerChart("chart",c,OPT);'
               'addEventListener("resize",function(){c.resize()});')
    schema = json.dumps({
        '@context': 'https://schema.org', '@type': 'Dataset',
        'name': f'شهریه مدارس غیردولتی {p} (نمایشی ۱۴۰۵)',
        'description': f'آمار شهریه {pdata["n_schools"]} مدرسه غیردولتی استان {p}',
        'inLanguage': 'fa'}, ensure_ascii=False)
    return (PROVINCE_PAGE_TMPL
            .replace('__TITLE__', f'شهریه مدارس غیردولتی {p} | داشبورد')
            .replace('__DESC__', f'آمار شهریه {pdata["n_schools"]} مدرسه غیردولتی {p} به تفکیک ناحیه — میانه، گران‌ترین‌ها.')
            .replace('__FONT__', FONT_CSS)
            .replace('__ECHARTS__', ECHARTS_JS)
            .replace('__NAV__', nav_html('../'))
            .replace('__H1__', f'🏫 شهریه مدارس غیردولتی {p}')
            .replace('__SUB__', f'{fa_num(pdata["n_schools"])} مدرسه · {fa_num(pdata["n_districts"])} ناحیه · مقادیر ۱۴۰۵، در نبود ۱۴۰۵: ۱۴۰۴')
            .replace('__CARDS__', cards)
            .replace('__NDIST__', fa_num(pdata['n_districts']))
            .replace('__DROWS__', drows)
            .replace('__TROWS__', trows)
            .replace('__DATAJS__', datajs)
            .replace('__CHARTJS__', chartjs)
            .replace('__FOOT__', foot_html())
            .replace('__SCHEMA__', schema))


def district_page(p, d, slug, pslug, rows, med, n1405):
    """rows: modal-ready lite dicts, priciest-first. Click any school for profile."""
    cards = (f'<div class="card"><b>{fa_num(len(rows))}</b><span>مدرسه</span></div>'
             f'<div class="card"><b>{fa_num(med)}</b><span>میانه آخرین شهریه ثبت‌شده (ریال)</span></div>'
             f'<div class="card"><b>{fa_num(n1405)}</b><span>ثبت‌شده ۱۴۰۵</span></div>')

    def trow(k, r):
        return (f'<tr><td>{fa_num(k + 1)}</td>'
                f'<td><a href="#" data-sid="{r["id"]}">{r["n"]}</a></td>'
                f'<td>{r["s"]}</td><td>{disp_cell(r["dt"], r["dy"])}</td></tr>')

    trows = ''.join(trow(k, r) for k, r in enumerate(rows[:20]))
    arows = ''.join(
        f'<tr><td>{fa_num(k + 1)}</td>'
        f'<td><a href="#" data-sid="{r["id"]}">{r["n"]}</a></td>'
        f'<td>{r["s"]}</td><td>{r["g"]}</td>'
        f'<td>{disp_cell(r["dt"], r["dy"])}</td></tr>'
        for k, r in enumerate(rows))
    datajs = clickable_rows_js(rows)
    top15 = rows[:15]
    chartjs = ('var el=document.getElementById("chart");var c=echarts.init(el);'
               'var OPT={textStyle:{fontFamily:"Vazirmatn,Tahoma,sans-serif"},'
               'tooltip:{trigger:"item",valueFormatter:function(v){return DSH.faNum(v)+" ریال"}},'
               'xAxis:{type:"value",axisLabel:{formatter:function(v){return DSH.faNum(v)}}},'
               'yAxis:{type:"category",data:'
               + json.dumps([r['n'] for r in top15], ensure_ascii=False) +
               '},series:[{type:"bar",data:'
               + json.dumps([r['dt'] or 0 for r in top15]) +
               ',itemStyle:{color:"#1a7f5a"}}],grid:{containLabel:true}};'
               'c.setOption(OPT);DSH.registerChart("chart",c,OPT);'
               'addEventListener("resize",function(){c.resize()});')
    return (DISTRICT_PAGE_TMPL
            .replace('__TITLE__', f'{d} ({p}) | جزییات ناحیه')
            .replace('__DESC__', f'جزییات شهریه ناحیه {d} {p}: {len(rows)} مدرسه، میانه و همه مدارس با پروفایل.')
            .replace('__FONT__', FONT_CSS)
            .replace('__ECHARTS__', ECHARTS_JS)
            .replace('__NAV__', nav_html('../'))
            .replace('__H1__', f'📍 ناحیه {d}')
            .replace('__SUB__', f'استان <a href="../provinces/{pslug}.html">{p}</a> · '
                                f'{fa_num(len(rows))} مدرسه · مقادیر ۱۴۰۵، در نبود ۱۴۰۵: ۱۴۰۴')
            .replace('__CARDS__', cards)
            .replace('__TROWS__', trows)
            .replace('__N__', fa_num(len(rows)))
            .replace('__AROWS__', arows)
            .replace('__DATAJS__', datajs)
            .replace('__CHARTJS__', chartjs)
            .replace('__FOOT__', foot_html()))


if __name__ == '__main__':
    main()
