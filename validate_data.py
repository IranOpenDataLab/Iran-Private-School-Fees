# -*- coding: utf-8 -*-
"""Validate scraped data: parse integrity, errors, blank-field rates."""
import sys, io, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

out = {}

def count_lines(path):
    n = 0
    with open(path, 'r', encoding='utf-8') as f:
        for n, _ in enumerate(f, 1):
            pass
    return n

def validate_jsonl(path, checks):
    """checks: dict name -> predicate(record)"""
    total = bad_parse = 0
    stats = {k: 0 for k in checks}
    samples = {k: [] for k in checks}
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                bad_parse += 1
                continue
            for name, pred in checks.items():
                try:
                    ok = pred(rec)
                except Exception:
                    ok = False
                if ok:
                    stats[name] += 1
                elif len(samples[name]) < 2:
                    samples[name].append(rec.get('school_path') or rec.get('item', {}).get('school_path'))
    return {'total': total, 'bad_parse': bad_parse, 'ok': stats, 'fail_samples': samples}

# ---- 1. schools_list.jsonl ----
out['list'] = validate_jsonl('checkpoint/schools_list.jsonl', {
    'has_path': lambda r: bool(r.get('item', {}).get('school_path')),
    'has_name': lambda r: bool(r.get('item', {}).get('school_name')),
    'has_context': lambda r: bool(r.get('province') and r.get('district')),
    'tuition_field_present': lambda r: r.get('item', {}).get('tution') is not None,
})

# ---- 2. details.jsonl ----
out['details'] = validate_jsonl('checkpoint/details.jsonl', {
    'no_error_detail': lambda r: '__error__' not in (r.get('detail') or {}),
    'detail_has_school': lambda r: bool((r.get('detail') or {}).get('school')),
    'detail_has_manager_or_founder': lambda r: bool(
        ((r.get('detail') or {}).get('school') or {}).get('fname') or
        (((r.get('detail') or {}).get('school') or {}).get('founder') or {}).get('fname')),
    'licenses_ok': lambda r: '__error__' not in (r.get('licenses') or {}) and 'school' in (r.get('licenses') or {}),
    'licenses_nonempty': lambda r: bool((((r.get('licenses') or {}).get('school') or {}).get('licenses'))),
    'tuition_hist_ok': lambda r: '__error__' not in (r.get('tuition_history') or {}) and 'tuition_history' in (r.get('tuition_history') or {}),
    'tuition_hist_nonempty_year': lambda r: any(v for v in (((r.get('tuition_history') or {}).get('tuition_history')) or {}).values()),
})

# ---- 3. log scan: errors/warnings/rate-limit ----
log_err = {'warning': 0, 'error': 0, 'giving_up': 0, 'rate_limit': 0, 'backoff': 0}
pat = re.compile(r'(WARNING|ERROR|GIVING UP|429|rate.?limit|Too Many)', re.I)
with open('scraper_log.txt', 'r', encoding='utf-8', errors='replace') as f:
    for line in f:
        if 'Phase' in line or 'Details progress' in line or 'rows' in line or 'no schools' in line:
            continue
        m = pat.search(line)
        if m:
            k = m.group(0).lower()
            if 'warning' in k: log_err['warning'] += 1
            elif 'giving' in k: log_err['giving_up'] += 1
            elif '429' in k or 'rate' in k or 'many' in k: log_err['rate_limit'] += 1
            else: log_err['error'] += 1
out['log'] = log_err

# ---- 4. current speed ----
import os, time
d_path = 'checkpoint/details.jsonl'
n1 = count_lines(d_path)
t1 = time.time()
time.sleep(10)
n2 = count_lines(d_path)
out['speed'] = {'schools_in_10s': n2 - n1, 'per_school_sec': round(10 / max(1, n2 - n1), 2), 'total_now': n2}

# ---- 5. exported files integrity ----
try:
    import pandas as pd
    df = pd.read_parquet('schools_data.parquet')
    out['export_parquet'] = {'records': int(df.shape[0]), 'cols': int(df.shape[1]),
                             'raw_cols': [c for c in df.columns if c.startswith('raw_')],
                             'parse': 'OK'}
except Exception as e:
    out['export_parquet'] = {'parse': f'FAIL: {e}'}

try:
    import csv as _csv
    with open('schools_data.csv', 'r', encoding='utf-8-sig', newline='') as f:
        rd = list(_csv.DictReader(f))
    out['export_csv'] = {'records': len(rd),
                         'cols': len(rd[0]) if rd else 0,
                         'parse': 'OK'}
    # cleaning invariants
    num_paren = re.compile(r'\(\d+\)')
    bad_province = sum(1 for r in rd if num_paren.search(r.get('province') or ''))
    bad_district = sum(1 for r in rd if num_paren.search(r.get('district') or ''))
    bad_confirm = sum(1 for r in rd if r.get('confirm_tuition') not in ('True', 'False'))

    # money sanity: money cols must be dot-free (integers / site text),
    # extra_hour may hold fractional hours ('7.5') but no BigDecimal tails,
    # totals == tuition + extra_curricular (blank component = 0)
    money_cols = [f'{y}_{p}' for y in ('1403', '1404', '1405')
                  for p in ('tuition', 'extra_curricular', 'total')]
    money_cols.append('1405_final_tuition')
    hour_cols = [f'{y}_extra_hour' for y in ('1403', '1404', '1405')]

    def _num(s):
        s = (s or '').strip()
        return int(s) if re.fullmatch(r'-?\d+', s) else None

    noise = bad_hour = bad_total = checked_total = 0
    for r in rd:
        for c in money_cols:
            if '.' in (r.get(c) or ''):
                noise += 1
        for c in hour_cols:
            hv = (r.get(c) or '').strip()
            if '.' in hv and not re.fullmatch(r'-?\d+\.\d{1,6}', hv):
                bad_hour += 1
        for y in ('1403', '1404', '1405'):
            t_raw = (r.get(f'{y}_tuition') or '').strip()
            e_raw = (r.get(f'{y}_extra_curricular') or '').strip()
            tot_raw = (r.get(f'{y}_total') or '').strip()
            t, e = _num(t_raw), _num(e_raw)
            if t is not None and e is not None:
                checked_total += 1
                if _num(tot_raw) != t + e:
                    bad_total += 1
            elif t is not None and not e_raw:
                checked_total += 1        # tuition only -> total = tuition
                if _num(tot_raw) != t:
                    bad_total += 1
            elif e is not None and not t_raw:
                checked_total += 1        # extra only -> total = extra
                if _num(tot_raw) != e:
                    bad_total += 1
            elif not t_raw and not e_raw and tot_raw:
                bad_total += 1
            elif ((t_raw and t is None) or (e_raw and e is None)) and tot_raw:
                bad_total += 1            # pending text -> total must be empty

    out['cleaning'] = {
        'province_with_numeric_code': bad_province,
        'district_with_numeric_code': bad_district,
        'confirm_not_bool': bad_confirm,
        'money_decimal_noise': noise,
        'hour_bad_format': bad_hour,
        'totals_checked': checked_total,
        'bad_total_rows': bad_total,
        'stage_sample': sorted({r.get('stage') for r in rd}),
        'status_labels': sorted({r.get('process_status_label') for r in rd}),
    }
except Exception as e:
    out['export_csv'] = {'parse': f'FAIL: {e}'}

print(json.dumps(out, ensure_ascii=False, indent=2))
