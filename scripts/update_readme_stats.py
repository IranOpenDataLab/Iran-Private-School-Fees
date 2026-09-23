# -*- coding: utf-8 -*-
"""
Regenerate the stats block in README.md AND README-EN.md between:
    <!-- STATS:START -->  ...  <!-- STATS:END -->
Data source: schools_data.csv (and file sizes). Last-update comes from the
last git commit of schools_data.csv (falls back to file mtime) and is shown
both in Solar Hijri (Jalali) and Gregorian dates.

The table is wrapped in <div dir="ltr"> so it keeps its column order inside
the RTL rendering of the Persian README (GitHub decides direction from the
first strong character of the page).
"""
import csv
import io
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README = os.path.join(ROOT, 'README.md')
README_EN = os.path.join(ROOT, 'README-EN.md')
CSV_PATH = os.path.join(ROOT, 'schools_data.csv')
PARQUET_PATH = os.path.join(ROOT, 'schools_data.parquet')

START = '<!-- STATS:START -->'
END = '<!-- STATS:END -->'

# stable display order of stage / process-status values (keys are Persian labels)
STAGE_ORDER = ['ابتدایی', 'ابتدایی استثنایی', 'متوسطه دوره اول',
               'متوسطه دوره دوم شاخه نظری',
               'متوسطه دوره دوم شاخه فنی و حرفه‌ای', 'متوسطه دوره دوم شاخه کاردانش']
STATUS_ORDER = ['ابلاغ شهریه', 'ابلاغ شهریه - در انتظار تایید',
                'تکمیل شده توسط موسس', 'در انتظار تکمیل موسس',
                'تایید کارشناس مسئول منطقه', 'رد شده توسط کارشناس مسئول منطقه',
                'رد شده توسط کارشناس مسئول استان', 'عدم ثبت درخواست شهریه']

STAGE_EN = {
    'ابتدایی': 'Primary',
    'ابتدایی استثنایی': 'Primary (special needs)',
    'متوسطه دوره اول': 'Lower secondary',
    'متوسطه دوره دوم شاخه نظری': 'Upper secondary – theoretical',
    'متوسطه دوره دوم شاخه فنی و حرفه‌ای': 'Upper secondary – technical & vocational',
    'متوسطه دوره دوم شاخه کاردانش': 'Upper secondary – Kardanesh',
    'نامشخص': 'Unknown',
}
STATUS_EN = {
    'ابلاغ شهریه': 'Tuition announced',
    'ابلاغ شهریه - در انتظار تایید': 'Announced – pending confirmation',
    'تکمیل شده توسط موسس': 'Completed by founder',
    'در انتظار تکمیل موسس': 'Awaiting founder completion',
    'تایید کارشناس مسئول منطقه': 'Approved by district expert',
    'رد شده توسط کارشناس مسئول منطقه': 'Rejected by district expert',
    'رد شده توسط کارشناس مسئول استان': 'Rejected by province expert',
    'عدم ثبت درخواست شهریه': 'No tuition request filed',
    'نامشخص': 'Unknown',
}


def fmt_fa(n):
    """Persian thousands separator, e.g. 24,648 -> 24٬648."""
    return f'{n:,}'.replace(',', '٬')


def fmt_en(n):
    return f'{n:,}'


def persian_digits(s):
    return ''.join('۰۱۲۳۴۵۶۷۸۹'[int(c)] if c.isdigit() else c for c in s)


def to_jalali(gy, gm, gd):
    """Gregorian (y, m, d) -> Jalali (y, m, d). Standard arithmetic algorithm."""
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621
    gy2 = gy + 1 if gm > 2 else gy
    days = (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100) \
        + ((gy2 + 399) // 400) - 80 + gd + g_d_m[gm - 1]
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + days % 31
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + (days - 186) % 30
    return jy, jm, jd


def last_update():
    """Last commit time of schools_data.csv (in the commit's own timezone), else file mtime."""
    try:
        out = subprocess.run(
            ['git', 'log', '-1', '--format=%cI', '--', 'schools_data.csv'],
            cwd=ROOT, capture_output=True, text=True, timeout=30,
        )
        ts = out.stdout.strip()
        if ts:
            # keep the commit's local wall time, no timezone conversion
            return datetime.fromisoformat(ts).strftime('%Y-%m-%d %H:%M')
    except Exception:
        pass
    mtime = datetime.fromtimestamp(os.path.getmtime(CSV_PATH), tz=timezone.utc)
    return mtime.astimezone().strftime('%Y-%m-%d %H:%M')


def jalali_of(updated):
    y, m, d = updated.split(' ')[0].split('-')
    jy, jm, jd = to_jalali(int(y), int(m), int(d))
    return f'{jy:04d}/{jm:02d}/{jd:02d}'


def collect_stats():
    total = with_license = with_history = 0
    provinces, districts = set(), set()
    confirmed = 0
    stages = {}
    statuses = {}

    with open(CSV_PATH, 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            if row.get('province'):
                provinces.add(row['province'])
            # cleaned district names repeat across provinces -> count pairs
            if row.get('district'):
                districts.add((row.get('province'), row['district']))
            try:
                if int(row.get('licenses_count') or 0) > 0:
                    with_license += 1
            except ValueError:
                pass
            if row.get('1403_tuition') or row.get('1404_tuition') or row.get('1405_final_tuition'):
                with_history += 1
            if str(row.get('confirm_tuition', '')).lower() == 'true':
                confirmed += 1
            st = row.get('stage') or 'نامشخص'
            stages[st] = stages.get(st, 0) + 1
            sl = row.get('process_status_label') or 'نامشخص'
            statuses[sl] = statuses.get(sl, 0) + 1

    def sz(path):
        if os.path.exists(path):
            mb = os.path.getsize(path) / (1024 * 1024)
            return f'{mb:.1f} MB'
        return '—'

    updated = last_update()
    return {
        'total': total,
        'provinces': len(provinces),
        'districts': len(districts),
        'with_license': with_license,
        'with_history': with_history,
        'confirmed': confirmed,
        'stages': stages,
        'statuses': statuses,
        'updated': updated,
        'jalali': jalali_of(updated),
        'csv_size': sz(CSV_PATH),
        'parquet_size': sz(PARQUET_PATH),
    }


def build_lines(counts, order, trans, num):
    line = ' · '.join(f'{trans.get(k, k)} {num(counts[k])}' for k in order if k in counts)
    line += ''.join(f' · {trans.get(k, k)} {num(v)}'
                    for k, v in sorted(counts.items()) if k not in order)
    return line


def render(stats, lang='fa'):
    fa = lang == 'fa'
    num = fmt_fa if fa else fmt_en
    trans = ({}, {}) if fa else (STAGE_EN, STATUS_EN)
    stage_trans, status_trans = trans
    stage_line = build_lines(stats['stages'], STAGE_ORDER, stage_trans, num)
    status_line = build_lines(stats['statuses'], STATUS_ORDER, status_trans, num)

    def pct(part, whole):
        if not whole:
            return '0٪' if fa else '0%'
        return f'{part * 100 // whole}٪' if fa else f'{part * 100 // whole}%'

    j_disp = persian_digits(stats['jalali']) if fa else stats['jalali']
    date_cell = f'`{j_disp}` — `{stats["updated"]}`'

    if fa:
        return f'''| شاخص | مقدار |
|---|---:|
| 🏫 تعداد کل مدارس | **{num(stats['total'])}** |
| 🗺️ استان‌ها | {num(stats['provinces'])} |
| 📍 مناطق آموزشی | {num(stats['districts'])} |
| 📚 تفکیک مقطع | {stage_line} |
| 🧾 وضعیت فرایند شهریه | {status_line} |
| 📄 مدارس دارای مجوز | {num(stats['with_license'])} ({pct(stats['with_license'], stats['total'])}) |
| 📊 مدارس دارای تاریخچه شهریه | {num(stats['with_history'])} ({pct(stats['with_history'], stats['total'])}) |
| ✅ شهریه تاییدشده ۱۴۰۵ | {num(stats['confirmed'])} ({pct(stats['confirmed'], stats['total'])}) |
| 🕐 آخرین به‌روزرسانی فایل داده | {date_cell} |
| 💾 حجم خروجی‌ها | CSV {stats['csv_size']} / Parquet {stats['parquet_size']} |'''

    return f'''| Indicator | Value |
|---|---:|
| 🏫 Total schools | **{num(stats['total'])}** |
| 🗺️ Provinces | {num(stats['provinces'])} |
| 📍 Education districts | {num(stats['districts'])} |
| 📚 Stage breakdown | {stage_line} |
| 🧾 Tuition process status | {status_line} |
| 📄 Schools with a license | {num(stats['with_license'])} ({pct(stats['with_license'], stats['total'])}) |
| 📊 Schools with tuition history | {num(stats['with_history'])} ({pct(stats['with_history'], stats['total'])}) |
| ✅ Confirmed tuition (1405) | {num(stats['confirmed'])} ({pct(stats['confirmed'], stats['total'])}) |
| 🕐 Last data update | {date_cell} |
| 💾 Output sizes | CSV {stats['csv_size']} / Parquet {stats['parquet_size']} |'''


def update_file(path, lang, stats):
    name = os.path.basename(path)
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    if START not in content or END not in content:
        print(f'ERROR: markers not found in {name}')
        sys.exit(1)

    block = f'{START}\n\n<div dir="ltr">\n\n{render(stats, lang)}\n\n</div>\n\n{END}'
    new = re.sub(re.escape(START) + r'.*?' + re.escape(END), lambda _: block, content, flags=re.S)

    if new != content:
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(new)
        print(f'{name}: stats updated')
    else:
        print(f'{name}: stats already up to date')


def main():
    stats = collect_stats()
    update_file(README, 'fa', stats)
    update_file(README_EN, 'en', stats)
    print()
    print(render(stats, 'fa'))


if __name__ == '__main__':
    main()
