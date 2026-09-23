# -*- coding: utf-8 -*-
"""
standalone cleaner for the scraped school DB (current CSV + re-exported Parquet).

Performs (ids from the review):
  2-1  province: strip trailing code+parens -> "شهر تهران(11)" -> "شهر تهران"
  2-2  district: keep only the area name    -> "تهران .منطقه 1(1101)" -> "منطقه 1"
  2-3  confirm_tuition: the two backend confirm tokens ("1rdc58xq30.b1b",
       "1rdc5g61nn.3e1") -> True ; "False"/"" -> False  (plain bool)
  2-4  process_status: documented Persian label column process_status_label
       (raw code kept in process_status)
  2-5  tuition columns chronological & year-first with '_' separators:
       1403_tuition, 1403_extra_curricular, 1403_extra_hour,
       1404_*, 1405_*  (1405 from the list phase keeps its own name set)
  2-6  per-year total = tuition + extra_curricular  -> 1403_total / 1404_total /
       1405_total
  3    stage: numeric stage_type_id -> Persian name (site labels)

Reads schools_data.csv, writes schools_data.csv (cleaned) and
schools_data.parquet (raw_* JSON-string columns for nested payloads).
The same functions are imported by run_scraper.phase_export so future
scrapes produce cleaned output directly.
"""
import csv
import json
import re
import sys
import io
from decimal import Decimal, ROUND_HALF_UP

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ---------------------------------------------------------------- constants

CONFIRM_TRUE_TOKENS = {'1rdc58xq30.b1b', '1rdc5g61nn.3e1'}

# raw process_status codes -> EXACT Persian labels of the dashboard's
# «وضعیت» column. Every label below was decoded from the portal UI itself
# (2026-09-23: seven targeted school-name searches covering codes '',1..6
# and both confirm states, e.g. سریر راستی='4', مسیر دانش='3', سمیع دانش='5',
# افق زرین تیله='2', شهید مدافع حرم محمدرضا دهقان='6', بوستان دانش='').
# Code '1' is confirm-dependent and is handled in process_label().
PROCESS_STATUS_LABELS = {
    '':  'عدم ثبت درخواست شهریه',
    '1': 'ابلاغ شهریه - در انتظار تایید',   # with confirm=False
    '2': 'تکمیل شده توسط موسس',
    '3': 'در انتظار تکمیل موسس',
    '4': 'تایید کارشناس مسئول منطقه',
    '5': 'رد شده توسط کارشناس مسئول منطقه',
    '6': 'رد شده توسط کارشناس مسئول استان',
}

# row-stage codes (API row field stage_type_id / stagetype_id) -> display name.
# NOTE: the UI dropdown sends a DIFFERENT enum [2,3,16,17] which the backend
# filters against ROW codes directly (bug) -> queries with it only return code
# '3'. Row codes below are verified from the site's own badges/dashboard:
#   3  <- dashboard column "دوره تحصیلی" = "دوره ابتدایی توصیفی"
#   5  <- school-details badge "دوره متوسطه اول"          (صاحب کوثر)
#   11 <- school-details badge "متوسطه دوم - نظری"        (امام جواد(ع))
#   12 <- school-details badge "متوسطه دوم - هنرستان فنی" (دانش فروزان2)
#   15 <- school-details badge "متوسطه دوم - هنرستان کاردانش" (دانش فروزان)
# Codes found by the wide probe (10 schools total):
#   31 <- details badge "ابتدايي استثناايي" AND license MainLevelName
#          "ابتدایی دوره اول و دوم استثنایی ..." (dual-source verified)
#   90/92 <- the site's badge renders the raw code (dictionary gap), but its
#          OWN license text says "متوسطه دوره اول ..." (one school each:
#          مهر و ماه / مکتب الصادق) -> mapped from that site-provided text.
STAGE_NAMES = {
    '3':  'ابتدایی',
    '5':  'متوسطه دوره اول',
    '11': 'متوسطه دوره دوم شاخه نظری',
    '12': 'متوسطه دوره دوم شاخه فنی و حرفه‌ای',
    '15': 'متوسطه دوره دوم شاخه کاردانش',
    '31': 'ابتدایی استثنایی',
    '90': 'متوسطه دوره اول',   # license-derived (site badge shows raw code)
    '92': 'متوسطه دوره اول',   # license-derived (site badge shows raw code)
}

# canonical chronological tuition column groups (post-rename)
YEAR_GROUPS = ['1403', '1404', '1405']
TUITION_PARTS = ['tuition', 'extra_curricular', 'extra_hour']

PARQUET_PATH = 'schools_data.parquet'

RENAME_MAP = {
    # list-phase cityیه (year 1405-1406 inquiry)
    'tuition_1405':            '1405_tuition',
    'extra_curricular_1405':   '1405_extra_curricular',
    'extra_hour_1405':         '1405_extra_hour',
    # tuition-history rows
    'tuition_1403':            '1403_tuition',
    'extra_curricular_1403':   '1403_extra_curricular',
    'extra_hour_1403':         '1403_extra_hour',
    'tuition_1404':            '1404_tuition',
    'extra_curricular_1404':   '1404_extra_curricular',
    'extra_hour_1404':         '1404_extra_hour',
    # detail-phase approved tuition for 1405-1406
    'tuition_1405_final':      '1405_final_tuition',
}

# final column order (42 cols incl. *_total and process_status_label)
COLUMN_ORDER = [
    'province', 'district', 'school_name', 'school_id', 'school_path',
    'school_url', 'gender', 'stage', 'address', 'manager',
    'founder', 'education_office_zone', 'education_office_province',
    'request_date', 'request_date_jalali', 'request_number', 'tracking_number',
    'license_holder', 'license_holder_national_code', 'license_operation',
    'license_level', 'license_province', 'license_zone', 'license_school_code',
    'license_portal_url', 'licenses_count',
    '1403_tuition', '1403_extra_curricular', '1403_extra_hour', '1403_total',
    '1404_tuition', '1404_extra_curricular', '1404_extra_hour', '1404_total',
    '1405_tuition', '1405_extra_curricular', '1405_extra_hour', '1405_total',
    '1405_final_tuition',
    'confirm_tuition', 'process_status', 'process_status_label',
]


# ---------------------------------------------------------------- cleaning

_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')


def normalize_money(v, money=True):
    """Tidy one tuition-history cell coming from the API.

    - integer strings (EN/FA digits, thousand commas) -> plain int string
    - BigDecimal zero tails ('595297500.000000...')    -> stripped
    - fractional MONEY ('692022770.833333...')         -> rounded to the
      nearest rial (HALF_UP): the server stores score-formula results as
      BigDecimal but rials have no sub-unit, and *_total must be an int
      that equals tuition + extra_curricular as displayed
    - fractional HOURS (money=False, extra_hour '7.5000') -> fraction only
      trimmed ('7.5'); hours are legitimately fractional (7.5 hours)
    - anything else (site text like «در انتظار تایید») -> unchanged
    """
    if not isinstance(v, str):
        return v
    out = v.strip()
    s = out.translate(_DIGITS).replace(',', '')
    m = re.fullmatch(r'(-?\d+)(?:\.(\d+))?', s)
    if not m:
        return out
    frac = m.group(2)
    if frac is None or not set(frac) - {'0'}:
        return m.group(1)               # integer, or .000... tail
    if money:
        return str(int(Decimal(s).quantize(Decimal('1'),
                                           rounding=ROUND_HALF_UP)))
    trimmed = frac.rstrip('0')          # hours: keep '7.5', drop '12.0000'
    return f'{m.group(1)}.{trimmed}' if trimmed else m.group(1)


def clean_province(value):
    """2-1: "شهر تهران(11)" -> "شهر تهران" """
    if not value:
        return value
    return re.sub(r'\(\d+\)\s*$', '', value).strip()


def clean_district(value):
    """2-2: "تهران .منطقه 1(1101)" -> "منطقه 1"  (area name only)

    Removes the parent prefix (everything before the first '.') and the
    trailing NUMERIC code "(1101)". A trailing paren containing TEXT, e.g.
    "مغان (گرمی )" / "پاوه (اورامانات )", is part of the site's official
    district name (city + bakhsh disambiguator) -> kept, only spaced tidy.
    """
    if not value:
        return value
    v = re.sub(r'\(\d+\)\s*$', '', value).strip()
    # split parent prefix at the site's dot separator
    dot = v.find('.')
    if dot >= 0:
        v = v[dot + 1:]
    # tidy spaces inside kept parens: "مغان (گرمی )" -> "مغان (گرمی)"
    v = re.sub(r'\(\s+', '(', v)
    v = re.sub(r'\s+\)', ')', v)
    return v.strip()


def clean_confirm(value):
    """2-3: backend token -> True, 'False'/'' -> False"""
    if value in (True, False):
        return value
    v = (value or '').strip()
    if v in CONFIRM_TRUE_TOKENS:
        return True
    if v in ('False', 'false', '', 'None', 'null'):
        return False
    if v in ('True', 'true'):
        return True
    return False


def process_label(code, confirmed=False):
    """2-4: raw code -> exact UI label.

    Code '1' renders as «ابلاغ شهریه» once the tuition is confirmed
    (confirm token present -> numeric tuition in the UI) and as
    «ابلاغ شهریه - در انتظار تایید» while it is not.
    Unknown codes are kept verbatim so they stand out."""
    key = (code or '').strip()
    if key == '1':
        return 'ابلاغ شهریه' if confirmed else 'ابلاغ شهریه - در انتظار تایید'
    return PROCESS_STATUS_LABELS.get(key, key or 'نامشخص')


def stage_name(code):
    """3: numeric stage code -> Persian name."""
    key = str(code or '').strip()
    return STAGE_NAMES.get(key, key or 'نامشخص')


def _int(v):
    """tuition cell -> int, or None when empty/non-numeric ('در انتظار تایید').

    Fractional money (server BigDecimal score results) is rounded to the
    nearest rial, mirroring normalize_money, so *_total always equals
    tuition + extra_curricular as displayed in the value columns."""
    if v is None or v == '':
        return None
    if isinstance(v, int):
        return v
    s = str(v).strip().translate(_DIGITS).replace(',', '')
    m = re.fullmatch(r'(-?\d+)(?:\.(\d+))?', s)
    if not m:
        return None
    frac = m.group(2)
    if frac is not None and set(frac) - {'0'}:
        return int(Decimal(s).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    return int(m.group(1))


def _blank(v):
    return v is None or str(v).strip() == ''


def add_totals(row):
    """2-6: 14xx_total = 14xx_tuition + 14xx_extra_curricular (int or None)

    Rules (verified against the UI, which sums the two money columns):
      - both parts numeric (or one numeric + the other BLANK/absent)
        -> sum, missing blank component counts as 0
      - any part present but non-numeric ('در انتظار تایید') -> None,
        because the amount is not known yet (never treat pending as 0)
      - both blank -> None
    """
    for y in YEAR_GROUPS:
        rt = row.get(f'{y}_tuition')
        re_ = row.get(f'{y}_extra_curricular')
        tn, en = _int(rt), _int(re_)
        pending = ((not _blank(rt)) and tn is None) or \
                  ((not _blank(re_)) and en is None)
        if pending or (_blank(rt) and _blank(re_)):
            row[f'{y}_total'] = None
        else:
            row[f'{y}_total'] = (tn or 0) + (en or 0)
    return row


def clean_row(row):
    """apply every transformation to one dict row"""
    row['province'] = clean_province(row.get('province'))
    row['district'] = clean_district(row.get('district'))
    row['confirm_tuition'] = clean_confirm(row.get('confirm_tuition'))
    row['process_status'] = str(row.get('process_status') or '').strip()
    row['process_status_label'] = process_label(
        row.get('process_status'), row['confirm_tuition'])
    # 3: stage as Persian name (raw code dropped from output on purpose)
    raw_stage = str(row.pop('stage_type_id', '') or '').strip()
    if raw_stage:
        row['stage'] = stage_name(raw_stage)
    elif not row.get('stage'):
        row['stage'] = 'نامشخص'
    # chronological year-first renames
    for old, new in RENAME_MAP.items():
        if old in row:
            row[new] = row.pop(old)
    # tuition money cells: strip BigDecimal zero tails and round sub-rial
    # fractions to whole rials; extra_hour keeps fractional hours ('7.5');
    # blanks -> None, site text («در انتظار تایید») stays verbatim
    for y in YEAR_GROUPS:
        for p in list(TUITION_PARTS) + ['final_tuition']:
            k = f'{y}_{p}'
            if k in row:
                v = normalize_money(row[k], money=(p != 'extra_hour'))
                row[k] = None if (v is None or str(v).strip() == '') else v
    return add_totals(row)


def finalize_row(row):
    """order + pad columns"""
    ordered = {k: row.get(k) for k in COLUMN_ORDER}
    for k in row:
        if k not in ordered and not k.startswith('raw_'):
            ordered[k] = row[k]
    for k, v in row.items():
        if k.startswith('raw_'):
            ordered[k] = v
    return ordered


def clean_rows(rows):
    return [finalize_row(clean_row(r)) for r in rows]


# ---------------------------------------------------------------- io helpers

def read_csv(path='schools_data.csv'):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write_csv(rows, path='schools_data.csv'):
    # CSV = the canonical 42 columns only; raw_* payloads live in Parquet
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(COLUMN_ORDER),
                           extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow(r)


def write_parquet(rows, path='schools_data.parquet'):
    import pandas as pd
    df = pd.DataFrame(rows)
    # raw_* payloads (nested dicts from the API) become JSON strings
    for c in df.columns:
        if c.startswith('raw_'):
            df[c] = df[c].apply(
                lambda v: v if isinstance(v, str) or v is None
                else json.dumps(v, ensure_ascii=False))
    df.to_parquet(path, index=False, engine='pyarrow')
    return df


def main():
    rows = read_csv()
    print(f'read {len(rows)} rows')
    cleaned = clean_rows(rows)
    write_csv(cleaned)
    print('wrote schools_data.csv (cleaned)')
    # The CSV never carries raw_* payloads; pull them from an existing
    # Parquet (keyed by school_path) so a standalone re-clean does not
    # silently drop them. Full rebuilds go through run_scraper export.
    try:
        import pandas as pd
        old = pd.read_parquet(PARQUET_PATH)
        raw_cols = [c for c in old.columns if c.startswith('raw_')]
        if raw_cols and 'school_path' in old.columns:
            raw_map = old.set_index('school_path')[raw_cols].to_dict('index')
            n = 0
            for r in cleaned:
                rp = raw_map.get(r.get('school_path'))
                if rp:
                    r.update(rp)
                    n += 1
            print(f'preserved raw_* payloads for {n} rows from existing parquet')
    except Exception as e:
        print('raw_* preservation skipped:', e)
    try:
        df = write_parquet(cleaned, PARQUET_PATH)
        print(f'wrote {PARQUET_PATH} ({df.shape[0]} x {df.shape[1]})')
    except ImportError as e:
        print('parquet skipped:', e)


if __name__ == '__main__':
    main()
