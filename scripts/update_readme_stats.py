# -*- coding: utf-8 -*-
"""
Regenerate the stats block in README.md between:
    <!-- STATS:START -->  ...  <!-- STATS:END -->
Data source: schools_data.csv (and file sizes). Last-update comes from the
last git commit of schools_data.csv (falls back to file mtime).
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
CSV_PATH = os.path.join(ROOT, 'schools_data.csv')
PARQUET_PATH = os.path.join(ROOT, 'schools_data.parquet')

START = '<!-- STATS:START -->'
END = '<!-- STATS:END -->'


def fmt_num(n):
    return f'{n:,}'.replace(',', '٬')  # Persian thousands separator


def last_update():
    """Last commit time of schools_data.csv, else file mtime."""
    try:
        out = subprocess.run(
            ['git', 'log', '-1', '--format=%cI', '--', 'schools_data.csv'],
            cwd=ROOT, capture_output=True, text=True, timeout=30,
        )
        ts = out.stdout.strip()
        if ts:
            return datetime.fromisoformat(ts).astimezone().strftime('%Y-%m-%d %H:%M')
    except Exception:
        pass
    mtime = datetime.fromtimestamp(os.path.getmtime(CSV_PATH), tz=timezone.utc)
    return mtime.astimezone().strftime('%Y-%m-%d %H:%M')


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

    # stable stage display order
    order = ['ابتدایی', 'ابتدایی استثنایی', 'متوسطه دوره اول',
             'متوسطه دوره دوم شاخه نظری',
             'متوسطه دوره دوم شاخه فنی و حرفه‌ای', 'متوسطه دوره دوم شاخه کاردانش']
    stage_line = ' · '.join(f'{k} {fmt_num(stages[k])}' for k in order if k in stages)
    stage_line += ''.join(f' · {k} {fmt_num(v)}' for k, v in sorted(stages.items()) if k not in order)

    # process_status distribution (labels verified against the site UI)
    status_order = ['ابلاغ شهریه', 'ابلاغ شهریه - در انتظار تایید',
                    'تکمیل شده توسط موسس', 'در انتظار تکمیل موسس',
                    'تایید کارشناس مسئول منطقه', 'رد شده توسط کارشناس مسئول منطقه',
                    'رد شده توسط کارشناس مسئول استان', 'عدم ثبت درخواست شهریه']
    status_line = ' · '.join(f'{k} {fmt_num(statuses[k])}' for k in status_order if k in statuses)
    status_line += ''.join(f' · {k} {fmt_num(v)}' for k, v in sorted(statuses.items())
                           if k not in status_order)

    return {
        'total': total,
        'provinces': len(provinces),
        'districts': len(districts),
        'with_license': with_license,
        'with_history': with_history,
        'confirmed': confirmed,
        'stage_line': stage_line,
        'status_line': status_line,
        'updated': last_update(),
        'csv_size': sz(CSV_PATH),
        'parquet_size': sz(PARQUET_PATH),
    }


def pct(part, whole):
    if not whole:
        return '0٪'
    return f'{part * 100 // whole}٪'


def render(stats):
    return f'''| شاخص | مقدار |
|---|---:|
| 🏫 تعداد کل مدارس | **{fmt_num(stats['total'])}** |
| 🗺️ استان‌ها | {fmt_num(stats['provinces'])} |
| 📍 مناطق آموزشی | {fmt_num(stats['districts'])} |
| 📚 تفکیک مقطع | {stats['stage_line']} |
| 🧾 وضعیت فرایند شهریه | {stats['status_line']} |
| 📄 مدارس دارای مجوز | {fmt_num(stats['with_license'])} ({pct(stats['with_license'], stats['total'])}) |
| 📊 مدارس دارای تاریخچه شهریه | {fmt_num(stats['with_history'])} ({pct(stats['with_history'], stats['total'])}) |
| ✅ شهریه تاییدشده ۱۴۰۵ | {fmt_num(stats['confirmed'])} ({pct(stats['confirmed'], stats['total'])}) |
| 🕐 آخرین به‌روزرسانی فایل داده | `{stats['updated']}` |
| 💾 حجم خروجی‌ها | CSV {stats['csv_size']} / Parquet {stats['parquet_size']} |'''


def main():
    with open(README, 'r', encoding='utf-8') as f:
        content = f.read()

    if START not in content or END not in content:
        print('ERROR: markers not found in README.md')
        sys.exit(1)

    stats = collect_stats()
    block = f'{START}\n{render(stats)}\n{END}'
    new = re.sub(re.escape(START) + r'.*?' + re.escape(END), lambda _: block, content, flags=re.S)

    if new != content:
        with open(README, 'w', encoding='utf-8') as f:
            f.write(new)
        print('README.md stats updated:')
    else:
        print('README.md stats already up to date:')
    print(render(stats))


if __name__ == '__main__':
    main()
