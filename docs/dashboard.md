# داشبورد مصورسازی شهریه مدارس غیردولتی (استاتیک، GitHub Pages)

> پیاده‌سازی مشخصات `docs/dashboard-spec.md` (v2). هیچ فایل موجودی ویرایش نشده؛
> همه‌چیز additive است و دیتاست (`schools_data.parquet`) فقط خوانده می‌شود.

## ساختار

| مسیر | نقش |
|---|---|
| `build_dashboard_data.py` | تنها اسکریپت داده: parquet ← `public/data/**` + صفحات استانی + sitemap |
| `dashboard-requirements.txt` | `pandas` + `pyarrow` (فقط سطح dashboard) |
| `public/index.html` | صفحه اصلی: KPI، روند، استان/مقطع/جنسیت، جست‌وجو، برترین‌ها |
| `public/network/index.html` | گراف شبکه همه ۲۴٬۶۴۸ مدرسه (ECharts، مختصات ازپیش‌محاسبه‌شده) |
| `public/assets/` | `style.css` + `common.js` مشترک |
| `public/data/**` | خروجی‌های JSON (ملی/استانی/مقطع/جنسیت/روند/جست‌وجو/گراف) |
| `public/provinces/*.html` | ۳۲ صفحه استاتیک استانی (سئو + Schema) — تولید اسکریپت |
| `reports/founder_clusters.csv` | خوشه‌های موسس (≥۲ مدرسه) برای بازبینی انسانی — خارج از `public/` |
| `.github/workflows/build-dashboard.yml` | انتشار opt-in با `workflow_dispatch` |

## اجرا (دستی، سالانه)

```bash
pip install -r dashboard-requirements.txt
python build_dashboard_data.py   # fail-fast + sanity asserts داخل خودش
python validate_data.py          # باید سبز بماند (دیتاست untouched)
```

سپس در تب Actions مخزن، workflow «Build dashboard» را با **Run workflow** اجرا کنید؛
شاخه `gh-pages` ساخته/به‌روز می‌شود. یک‌بار در Settings ← Pages منبع را
**Deploy from a branch → `gh-pages` / `/ (root)`** بگذارید.

## قراردادهای ثبت‌شده (audit)

- سال پایه رتبه‌بندی/اندازه گره/یال: `1404_total`.
- اندازه گره مدرسه در گراف: `3 + 25·√(total_1404 / max_total_1404)` (در `graph/full.json → meta.size_rule`).
- چیدمان آفلاین قطعی (`SEED=1405` ثبت‌شده؛ بدون RNG): استان‌ها روی دایره بزرگ →
  ناحیه‌ها روی دایره استانی → مدارس روی حلقه زاویه‌طلایی دور ناحیه + ۲۵٪ کشش به
  مرکز خوشه موسس. اجرای مجدد **byte-identical** است.
- یال موسس زنجیره‌ای (`i−1 → i` در هر خوشه، مرتب‌شده): سبز ضخیم = نام نرمال‌شده
  یکسان، خط‌چین = نام متفاوت. یال ناحیه: نازک خاکستری کم‌رنگ.
- فیلترهای مقطع/جنسیت فقط **کم‌رنگ** می‌کنند (opacity)؛ هیچ گرهی حذف نمی‌شود و
  شمارنده «نمایش X از ۲۴٬۶۴۸» همیشه دیده می‌شود.
- نرمال‌سازی ی/ک/ه + ارقام فارسی هم در ایندکس پایتون هم در کوئری JS یکسان است.
- هشدار پوشش ۱۴۰۵: اگر سهم مدارس دارای `1405_total` زیر ۶۰٪ باشد،
  `coverage_1405_warning=true` و کارت هشدار نمایش داده می‌شود.
- محدودیت بودجه (§4): صفحه اصلی lazy نیست و زیر ۵۰۰KB می‌ماند (بزرگ‌ترین فچ
  اولیه `top.json` با ۱۳۹KB)؛ `search-index.json` (∼۵MB) فقط با اولین جست‌وجو،
  و `graph/full.json` (∼۳٫۱MB) فقط در صفحه `/network/` لود می‌شود
  (network page: initial ≤ ۱MB، داده کامل on interaction).

## پذیرش (§6) — نتایج اجرای محلی

| چک | نتیجه |
|---|---|
| `validate_data.py` سبز، بدون diff دیتاست | ✅ exit 0 |
| همه خروجی‌های ۲.۲ و ۲.۳ تولید شدند | ✅ (لیست در لاگ اسکریپت) |
| مجموع `by-province` == ۲۴٬۶۴۸؛ گراف ۲۴٬۶۴۸؛ ایندکس ۲۴٬۶۴۸ | ✅ assert داخل اسکریپت + workflow |
| اجرای مجدد byte-identical | ✅ (sha256 `full.json` یکسان) |
| فقط CDN خارجی: ECharts + Fuse.js + Vazirmatn | ✅ |
