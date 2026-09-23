# 🏫 استخراج داده مدارس غیردولتی — شهریه ۱۴۰۵-۱۴۰۶

استخراج کامل داده مدارس غیردولتی از سامانه‌های
[`portal.mosharekatha.ir`](https://portal.mosharekatha.ir/dashboard/school-tuition) و
[`my.mosharekatha.ir`](https://my.mosharekatha.ir) — شامل لینک مدرسه، مشخصات، مجوز،
جزئیات مالکیت/موقعیت و شهریه مصوب/فوق‌برنامه.

> همه درخواست‌ها **بدون لاگین** و با رمزگشایی پاسخ AES-256-CBC سامانه انجام می‌شود
> (پروتکل در `scraper.py` پیاده‌سازی شده).

---

## 📊 آمار مخزن

<!-- STATS:START -->
| شاخص | مقدار |
|---|---:|
| 🏫 تعداد کل مدارس | **13٬768** |
| 🗺️ استان‌ها | 32 |
| 📍 مناطق آموزشی | 542 |
| 📄 مدارس دارای مجوز | 8٬491 (61٪) |
| 📊 مدارس دارای تاریخچه شهریه | 11٬781 (85٪) |
| ✅ شهریه تاییدشده ۱۴۰۵ | 0 (0٪) |
| 🕐 آخرین به‌روزرسانی فایل داده | `2026-09-23 13:52` |
| 💾 حجم خروجی‌ها | CSV 10.1 MB / JSON 47.3 MB |
<!-- STATS:END -->

> ✨ این بخش با هر به‌روزرسانی مخزن، توسط [GitHub Action](.github/workflows/update-stats.yml)
> به‌صورت خودکار از روی `schools_data.csv` بازتولید می‌شود.

---

## 📁 ساختار پروژه

| فایل/پوشه | توضیح |
|---|---|
| `scraper.py` | هسته: رمزگشایی AES پاسخ‌ها + توابع API (مناطق، لیست مدارس، جزئیات، مجوز، تاریخچه شهریه) |
| `run_scraper.py` | اجرای سه‌فازی با قابلیت ادامه (resumable): `list` → `details` → `export` |
| `validate_data.py` | اعتبارسنجی داده: سلامت JSONL، نرخ خطا، نرخ فیلدهای خالی |
| `scripts/update_readme_stats.py` | تولید خودکار بخش آمار README |
| `.github/workflows/update-stats.yml` | Action به‌روزرسانی آمار در هر push |
| `schools_data.csv` | **خروجی نهایی** — ۳۸ ستون، UTF-8-BOM (مناسب اکسل) |
| `schools_data.json` | همون خروجی + payload خام API (`raw_detail`، `raw_licenses`، `raw_tuition_history`) |
| `metadata.md` | توضیح کامل هر ۳۸ ستون + منبع هر فیلد + نکات |
| `checkpoint/` | نقطه ازسرگیری (قابلیت ادامه بعد از قطعی) |
| `scraper_log.txt` | لاگ اجرای کامل |

---

## 🚀 نحوه اجرا

```bash
pip install requests pycryptodome

python run_scraper.py list      # فاز ۱: مناطق + لیست همه مدارس (۱۵۷۰ منطقه-جنسیت)
python run_scraper.py details   # فاز ۲: جزئیات/مجوز/تاریخچه هر مدرسه (۳ درخواست)
python run_scraper.py export    # فاز ۳: ساخت CSV + JSON نهایی
python run_scraper.py all       # هر سه فاز پشت‌سرهم

python validate_data.py         # اعتبارسنجی داده‌های استخراج‌شده
```

- **قابلیت ادامه:** هر فاز در `checkpoint/` ذخیره می‌کند؛ اجرای دوباره از همان‌جا ادامه می‌دهد.
- **کنترل سرعت:** ثابت‌های `LIST_SLEEP` / `DETAIL_SLEEP` در بالای `run_scraper.py`.

---

## 🔌 API سامانه (خلاصه)

- endpoint: `POST {domain}/core-api/v1/data-provider/get-data-source`
- بدنه: `{serviceId, key, params}` — پاسخ: `{"token": "<base64>"}` که رمگشایی AES-256-CBC
  (قالب OpenSSL `Salted__`، کلید از `EvpBytesToKey` با MD5) می‌شود.
- بدون هدر `client-id`، سرور از کلید fallback استفاده می‌کند.
- کلیدهای داده (`key`):
  - `medungo-explore/get/sub-organs` — استان‌ها/مناطق (`organPath`)
  - `mosharekatha-portal/load/school-tuition-inquiry` — لیست مدرسه (`regionPath`, `gender`, `stage_id`, `year`, `limit`, `page`, `filters`)
  - `my-mosharekatha/school-panel/school-detail/load` — جزئیات مدرسه
  - `my-mosharekatha/school-panel/school-licenses/load` — مجوزها
  - `my-mosharekatha/school-panel/school-tuition-history/load` — تاریخچه شهریه (۱۴۰۳/۱۴۰۴/۱۴۰۵)
- لینک درگاه ملی مجوزها: `https://qr.mojavez.ir/track/{RequestNumber}`

---

## ⚙️ به‌روزرسانی خودکار آمار

با هر push به شاخه `main` (تغییر داده یا اسکریپت)، Action زیر اجرا می‌شود:

1. `scripts/update_readme_stats.py` آمار را از `schools_data.csv` می‌خواند
2. بخش بین `<!-- STATS:START -->
| شاخص | مقدار |
|---|---:|
| 🏫 تعداد کل مدارس | **13٬768** |
| 🗺️ استان‌ها | 32 |
| 📍 مناطق آموزشی | 542 |
| 📄 مدارس دارای مجوز | 8٬491 (61٪) |
| 📊 مدارس دارای تاریخچه شهریه | 11٬781 (85٪) |
| ✅ شهریه تاییدشده ۱۴۰۵ | 0 (0٪) |
| 🕐 آخرین به‌روزرسانی فایل داده | `2026-09-23 13:52` |
| 💾 حجم خروجی‌ها | CSV 10.1 MB / JSON 47.3 MB |
<!-- STATS:END -->` را بازنویسی می‌کند
3. در صورت تغییر، commit و push می‌کند

---

## 📌 نکته‌ها

- واحد پول: **ریال** (مقادیر به‌صورت رشته).
- ~۶۲٪ مدارس مجوز ثبت‌شده دارند؛ بقیه واقعاً مجوزی ثبت نکرده‌اند (طبیعی).
- `stage_id`: `2`=ابتدایی، `3`=متوسطه اول، `16`=متوسطه دوم نظری، `17`=فنی و حرفه‌ای/کاردانش.
- `gender`: `1`=پسرانه، `2`=دخترانه.
- توضیح کامل ستون‌ها: [`metadata.md`](metadata.md)
