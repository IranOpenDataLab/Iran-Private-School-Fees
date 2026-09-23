# -*- coding: utf-8 -*-
"""
Full scraper for portal.mosharekatha.ir (non-governmental schools, year 1405-1406)

Phases:
  1. Collect district lists + full school lists (province -> district -> gender -> page)
  2. Collect per-school details (detail + licenses + tuition history)
  3. Export merged data to cleaned CSV (UTF-8-BOM for Excel) + Parquet
     (raw_* API payloads live only in the Parquet file)

Resumable: progress is checkpointed under ./checkpoint/
Run:  python run_scraper.py [phase]     phase = list | details | export | all (default)
"""
import sys
import os
import io
import json
import csv
import time
import random
import logging
import threading

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from scraper import (
    get_provinces, get_districts, get_schools,
    get_school_detail, get_school_licenses, get_tuition_history,
)

# ------------------------------------------------------------
# CONFIG - keep it slow to avoid rate limiting
# ------------------------------------------------------------
LIST_SLEEP = 0.02        # seconds between school-list page requests
STEP_SLEEP = 0.01        # seconds between small steps (district fetch etc.)
DETAIL_SLEEP = 0.02      # seconds between detail API requests
ERROR_BACKOFF = 10       # seconds to wait after an unexpected error
MAX_COMBO_RETRIES = 3    # retries per district+gender combo on hard errors

BASE = os.path.dirname(os.path.abspath(__file__))
CKPT = os.path.join(BASE, 'checkpoint')
os.makedirs(CKPT, exist_ok=True)

F_DISTRICTS = os.path.join(CKPT, 'districts.json')
F_LIST = os.path.join(CKPT, 'schools_list.jsonl')
F_LIST_DONE = os.path.join(CKPT, 'list_done.txt')
F_DETAILS = os.path.join(CKPT, 'details.jsonl')
F_LOG = os.path.join(BASE, 'scraper_log.txt')

GENDER_LABEL = {'1': 'پسرانه', '2': 'دخترانه'}

# Real ROW stage codes are [3,5,11,12,15] (verified from the site's own
# badges/dashboard: ابتدایی / متوسطه اول / نظری / هنرستان فنی / کاردانش).
# The UI dropdown's enum [2,3,16,17] is a DIFFERENT mapping the backend
# filters against row codes directly -> queries with it only ever returned
# code '3' (ابتدایی) rows. Probe 0..99 so no future/unknown code is missed.
WIDE_STAGE_IDS = [str(i) for i in range(0, 100)]

# ------------------------------------------------------------
# LOGGING
# ------------------------------------------------------------
log = logging.getLogger('scraper')
log.setLevel(logging.INFO)
_fmt = logging.Formatter('%(asctime)s %(levelname)s %(message)s', '%H:%M:%S')
_fh = logging.FileHandler(F_LOG, encoding='utf-8')
_fh.setFormatter(_fmt)
_sh = logging.StreamHandler(sys.stdout)
_sh.setFormatter(_fmt)
log.addHandler(_fh)
log.addHandler(_sh)


def sleep(base):
    time.sleep(base + random.uniform(0.0, base * 0.5))


# ------------------------------------------------------------
# CHECKPOINT HELPERS
# ------------------------------------------------------------
def load_done(path):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return set(line.strip() for line in f if line.strip())
    return set()


def mark_done(path, key):
    with open(path, 'a', encoding='utf-8') as f:
        f.write(key + '\n')


def append_jsonl(path, obj):
    with open(path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(obj, ensure_ascii=False) + '\n')


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out


# ------------------------------------------------------------
# PHASE 1: districts + school lists
# ------------------------------------------------------------
def get_all_districts():
    """Fetch (and cache) districts for every province."""
    if os.path.exists(F_DISTRICTS):
        with open(F_DISTRICTS, 'r', encoding='utf-8') as f:
            return json.load(f)

    log.info('Fetching provinces...')
    provinces = get_provinces()
    sleep(STEP_SLEEP)

    result = []
    for p in provinces:
        pkey, pname = p['key'], p['title']
        districts = []
        for attempt in range(MAX_COMBO_RETRIES):
            try:
                districts = get_districts(pkey)
                break
            except Exception as e:
                log.warning('districts error for %s: %s (retry %d)', pname, e, attempt + 1)
                time.sleep(ERROR_BACKOFF)
        log.info('Province %s: %d districts', pname, len(districts))
        result.append({'province_key': pkey, 'province_name': pname, 'districts': districts})
        sleep(STEP_SLEEP)

    with open(F_DISTRICTS, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return result


def phase_list():
    """Collect every school row from every district (both genders), paginated."""
    tree = get_all_districts()
    done = load_done(F_LIST_DONE)

    total_combos = sum(len(pd['districts']) * 2 for pd in tree)
    log.info('Phase LIST: %d district+gender combos, %d already done', total_combos, len(done))

    n_rows = 0
    if os.path.exists(F_LIST):
        n_rows = sum(1 for _ in open(F_LIST, 'r', encoding='utf-8'))

    for pd in tree:
        for d in pd['districts']:
            dkey, dname = d['key'], d['title']
            for gender in ('1', '2'):
                combo = f'{dkey}|{gender}'
                if combo in done:
                    continue

                ok = False
                for attempt in range(MAX_COMBO_RETRIES):
                    try:
                        page = 1
                        fetched = 0
                        total = None
                        while True:
                            res = get_schools(dkey, gender=gender, page=page, limit=50,
                                              stage_ids=WIDE_STAGE_IDS)
                            items = res.get('items') or []
                            if total is None:
                                try:
                                    total = int(res.get('totalCount') or 0)
                                except (TypeError, ValueError):
                                    total = 0
                            if not items:
                                break
                            for it in items:
                                n_rows += 1
                                append_jsonl(F_LIST, {
                                    'province': pd['province_name'],
                                    'province_key': pd['province_key'],
                                    'district': dname,
                                    'district_key': dkey,
                                    'gender_query': gender,
                                    'item': it,
                                })
                            fetched += len(items)
                            if len(items) < 50:
                                break
                            page += 1
                            sleep(LIST_SLEEP)
                        log.info('%s %s: %d/%d rows (total rows: %d)',
                                 dname, GENDER_LABEL[gender], fetched, total or '?', n_rows)
                        ok = True
                        break
                    except ValueError as e:
                        msg = str(e)
                        if 'یافت نشد' in msg:
                            # no schools for this combo - normal end
                            log.info('%s %s: no schools', dname, GENDER_LABEL[gender])
                            ok = True
                            break
                        log.warning('%s %s page %d: API error (attempt %d): %s',
                                    dname, GENDER_LABEL[gender], page, attempt + 1, msg)
                        time.sleep(ERROR_BACKOFF)
                    except Exception as e:
                        log.warning('%s %s page %d: error (attempt %d): %s',
                                    dname, GENDER_LABEL[gender], page, attempt + 1, e)
                        time.sleep(ERROR_BACKOFF)

                if ok:
                    mark_done(F_LIST_DONE, combo)
                    sleep(STEP_SLEEP)
                else:
                    log.error('GIVING UP combo %s after %d attempts', combo, MAX_COMBO_RETRIES)

    done = load_done(F_LIST_DONE)
    log.info('Phase LIST finished: %d/%d combos done, %d rows', len(done), total_combos, n_rows)


# ------------------------------------------------------------
# PHASE 2: per-school details
# ------------------------------------------------------------
def safe_detail(path, fn):
    """Call a detail API fn(path) with retries; return dict or {'__error__': msg}."""
    last = None
    for attempt in range(MAX_COMBO_RETRIES):
        try:
            return fn(path)
        except ValueError as e:
            last = str(e)
            break                      # deterministic API error - don't hammer
        except Exception as e:
            last = str(e)
            time.sleep(ERROR_BACKOFF)
    return {'__error__': last}


def phase_details():
    rows = read_jsonl(F_LIST)
    seen = set()
    schools = []
    for r in rows:
        sp = r['item'].get('school_path')
        if sp and sp not in seen:
            seen.add(sp)
            schools.append(sp)

    done = set()
    if os.path.exists(F_DETAILS):
        for rec in read_jsonl(F_DETAILS):
            if 'school_path' in rec:
                done.add(rec['school_path'])

    todo = [sp for sp in schools if sp not in done]
    log.info('Phase DETAILS: %d unique schools, %d done, %d todo',
             len(schools), len(done), len(todo))

    errors = 0
    for i, sp in enumerate(todo, 1):
        rec = {'school_path': sp}
        rec['detail'] = safe_detail(sp, get_school_detail)
        sleep(DETAIL_SLEEP)
        rec['licenses'] = safe_detail(sp, get_school_licenses)
        sleep(DETAIL_SLEEP)
        rec['tuition_history'] = safe_detail(sp, get_tuition_history)
        sleep(DETAIL_SLEEP)

        if any('__error__' in (rec[k] or {}) for k in ('detail', 'licenses', 'tuition_history')):
            errors += 1
        append_jsonl(F_DETAILS, rec)

        if i % 50 == 0 or i == len(todo):
            log.info('Details progress: %d/%d (errors: %d)', i, len(todo), errors)

    log.info('Phase DETAILS finished: %d processed, %d with errors', len(todo), errors)


# ------------------------------------------------------------
# PHASE 3: export merged JSON + CSV
# ------------------------------------------------------------
def gregorian_to_jalali(gy, gm, gd):
    """Convert Gregorian date to Jalali (Persian) date."""
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy, gy = 979, gy - 1600
    else:
        jy, gy = 0, gy - 621
    gy2 = gy + 1 if gm > 2 else gy
    days = (365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100
            + (gy2 + 399) // 400 - 80 + gd + g_d_m[gm - 1])
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm, jd = 1 + days // 31, 1 + days % 31
    else:
        jm, jd = 7 + (days - 186) // 30, 1 + (days - 186) % 30
    return jy, jm, jd


def iso_to_jalali(s):
    if not s:
        return ''
    try:
        date_part = str(s)[:10]
        gy, gm, gd = (int(x) for x in date_part.split('-'))
        jy, jm, jd = gregorian_to_jalali(gy, gm, gd)
        return f'{jy:04d}/{jm:02d}/{jd:02d}'
    except Exception:
        return ''


def flatten_tuition_year(entry):
    """Normalize a tuition-history year entry (different key names per year)."""
    if not entry:
        return {'tution': '', 'extra_curricular': '', 'extra_hour': ''}
    return {
        'tution': entry.get('final_tuition') or entry.get('tution') or '',
        'extra_curricular': entry.get('final_extra_curricular') or entry.get('extra_curricular') or '',
        'extra_hour': entry.get('final_extra_hour') or entry.get('extra_hour') or '',
    }


def phase_export():
    rows = read_jsonl(F_LIST)
    details = {}
    for rec in read_jsonl(F_DETAILS):
        if 'school_path' in rec:
            details[rec['school_path']] = rec

    merged = []
    seen = set()
    for r in rows:
        it = r['item']
        sp = it.get('school_path')
        if not sp or sp in seen:
            continue
        seen.add(sp)

        rec = details.get(sp, {})
        det = (rec.get('detail') or {}).get('school') or {}
        lic_list = ((rec.get('licenses') or {}).get('school') or {}).get('licenses') or []
        hist = (rec.get('tuition_history') or {}).get('tuition_history') or {}
        lic = lic_list[0] if lic_list else {}

        founder = det.get('founder') or {}
        h1403 = flatten_tuition_year(hist.get('1403'))
        h1404 = flatten_tuition_year(hist.get('1404'))
        h1405 = flatten_tuition_year(hist.get('1405'))

        lic_link = (f"https://qr.mojavez.ir/track/{lic['RequestNumber']}"
                    if lic.get('RequestNumber') else '')

        merged.append({
            # --- basic / location ---
            'province': r['province'],
            'district': r['district'],
            'school_name': it.get('school_name'),
            'school_id': it.get('school_id'),
            'school_path': sp,
            'school_url': f'https://my.mosharekatha.ir/school-details/{sp}',
            'gender': GENDER_LABEL.get(str(it.get('gender')), it.get('gender')),
            'stage_type_id': it.get('stage_type_id'),
            'address': it.get('school', {}).get('addres') or det.get('address'),
            # --- ownership / management ---
            'manager': ' '.join(x for x in [det.get('fname'), det.get('lname')] if x),
            'founder': ' '.join(x for x in [founder.get('fname'), founder.get('lname')] if x),
            'education_office_zone': det.get('rg_name'),
            'education_office_province': det.get('prv_name'),
            # --- license / request ---
            'request_date': lic.get('DateRequest'),
            'request_date_jalali': iso_to_jalali(lic.get('DateRequest')),
            'request_number': lic.get('CodeRequest'),
            'tracking_number': lic.get('RequestNumber'),
            'license_holder': ' '.join(x for x in [lic.get('FirstName'), lic.get('SurName')] if x),
            'license_holder_national_code': lic.get('NationalCode'),
            'license_operation': lic.get('OperationName'),
            'license_level': lic.get('MainLevelName'),
            'license_province': lic.get('StateName'),
            'license_zone': lic.get('AreaName'),
            'license_school_code': lic.get('Code'),
            'license_portal_url': lic_link,
            'licenses_count': len(lic_list),
            # --- tuition 1405 (from list) ---
            'tuition_1405': it.get('tution'),
            'extra_curricular_1405': it.get('extra_curricular'),
            'extra_hour_1405': it.get('extra_hour'),
            'confirm_tuition': it.get('confirmTution'),
            'process_status': it.get('process_status'),
            # --- tuition history ---
            'tuition_1403': h1403['tution'],
            'extra_curricular_1403': h1403['extra_curricular'],
            'extra_hour_1403': h1403['extra_hour'],
            'tuition_1404': h1404['tution'],
            'extra_curricular_1404': h1404['extra_curricular'],
            'extra_hour_1404': h1404['extra_hour'],
            'tuition_1405_final': h1405['tution'],
            # --- raw payloads for reference ---
            'raw_detail': det or None,
            'raw_licenses': lic_list or None,
            'raw_tuition_history': hist or None,
        })

    # ---- cleaning pass (renames, province/district cleanup, confirm bool,
    #      process/stage labels, chronological order, *_total columns) ----
    from clean_data import clean_rows, COLUMN_ORDER
    cleaned = clean_rows(merged)

    # CSV: human/Excel friendly, no raw_* columns
    out_csv = os.path.join(BASE, 'schools_data.csv')
    with open(out_csv, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLUMN_ORDER, extrasaction='ignore')
        w.writeheader()
        for m in cleaned:
            w.writerow(m)

    # Parquet: full data incl. raw_* payloads (dicts serialized to JSON strings)
    from clean_data import write_parquet
    out_parquet = os.path.join(BASE, 'schools_data.parquet')
    df = write_parquet(cleaned, out_parquet)

    log.info('Phase EXPORT: %d schools -> %s (%d cols), %s',
             len(cleaned), out_csv, len(COLUMN_ORDER), out_parquet)


# ------------------------------------------------------------
if __name__ == '__main__':
    phase = (sys.argv[1] if len(sys.argv) > 1 else 'all').lower()
    started = time.time()
    try:
        if phase in ('list', 'all'):
            phase_list()
        if phase in ('details', 'all'):
            phase_details()
        if phase in ('export', 'all'):
            phase_export()
    except KeyboardInterrupt:
        log.warning('Interrupted - progress is saved, rerun to resume.')
    log.info('Done in %.1f min', (time.time() - started) / 60)
