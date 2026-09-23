# 🏫 استخراج داده مدارس غیردولتی — شهریه ۱۴۰۵-۱۴۰۶

> 🌐 **نسخه انگلیسی:** [README-EN.md](README-EN.md)

استخراج کامل داده مدارس غیردولتی از سامانه‌های
[`portal.mosharekatha.ir`](https://portal.mosharekatha.ir/dashboard/school-tuition) و
[`my.mosharekatha.ir`](https://my.mosharekatha.ir) — شامل لینک مدرسه، مشخصات، مجوز،
جزئیات مالکیت/موقعیت و شهریه مصوب/فوق‌برنامه.

---

## 📊 آمار مخزن

<!-- STATS:START -->

<div dir="ltr">

| شاخص | مقدار |
|---|---:|
| 🏫 تعداد کل مدارس | **24٬648** |
| 🗺️ استان‌ها | 32 |
| 📍 مناطق آموزشی | 558 |
| 📚 تفکیک مقطع | ابتدایی 13٬768 · ابتدایی استثنایی 8 · متوسطه دوره اول 5٬780 · متوسطه دوره دوم شاخه نظری 3٬532 · متوسطه دوره دوم شاخه فنی و حرفه‌ای 919 · متوسطه دوره دوم شاخه کاردانش 641 |
| 🧾 وضعیت فرایند شهریه | ابلاغ شهریه 13٬142 · ابلاغ شهریه - در انتظار تایید 4٬307 · تکمیل شده توسط موسس 640 · در انتظار تکمیل موسس 373 · تایید کارشناس مسئول منطقه 742 · رد شده توسط کارشناس مسئول منطقه 244 · رد شده توسط کارشناس مسئول استان 11 · عدم ثبت درخواست شهریه 5٬189 |
| 📄 مدارس دارای مجوز | 14٬198 (57٪) |
| 📊 مدارس دارای تاریخچه شهریه | 20٬988 (85٪) |
| ✅ شهریه تاییدشده ۱۴۰۵ | 13٬143 (53٪) |
| 🕐 آخرین به‌روزرسانی فایل داده | `۱۴۰۵/۰۷/۰۱` — `2026-09-23 18:10` |
| 💾 حجم خروجی‌ها | CSV 17.7 MB / Parquet 10.3 MB |

</div>

<!-- STATS:END -->

---

## 📁 ساختار پروژه

<div dir="ltr">

| فایل/پوشه | توضیح |
|---|---|
| `scraper.py` | هسته: رمزگشایی AES پاسخ‌ها + توابع API (مناطق، لیست مدارس، جزئیات، مجوز، تاریخچه شهریه) |
| `run_scraper.py` | اجرای سه‌فازی با قابلیت ادامه (resumable): `list` → `details` → `export` |
| `clean_data.py` | پاکسازی مستقل دیتای فعلی (نام استان/منطقه، بولین تایید، برچسب مقطع/وضعیت، مرتب‌سازی سالیانه ستون‌ها، ستون `*_total`) |
| `validate_data.py` | اعتبارسنجی داده: سلامت JSONL، نرخ خطا، سلامت خروجی CSV/Parquet |
| `scripts/update_readme_stats.py` | تولید خودکار بخش آمار `README.md` و `README-EN.md` |
| `RELEASE_NOTES.md` | متن توضیحات آخرین به‌روزرسانی که در Release منتشر می‌شود |
| `.github/workflows/update-stats.yml` | Action بازنویسی آمار هر دو README با هر push |
| `.github/workflows/release.yml` | Action انتشار آخرین `schools_data.csv` / `schools_data.parquet` در Release با هر push |
| `README-EN.md` | نسخه انگلیسی همین مستند |
| `schools_data.csv` | **خروجی نهایی** — ۴۲ ستون پاکسازی‌شده، UTF-8-BOM (مناسب اکسل) |
| `schools_data.parquet` | همون خروجی + ستون‌های `raw_detail` / `raw_licenses` / `raw_tuition_history` (JSON رشته‌ای) |
| `metadata.md` | توضیح کامل هر ستون + منبع هر فیلد + رمزگشایی کدها |
| `checkpoint/` | نقطه ازسرگیری (قابلیت ادامه بعد از قطعی) |
| `scraper_log.txt` | لاگ اجرای کامل |

</div>

---

## 🚀 نحوه اجرا

<div dir="ltr">

```bash
pip install requests pycryptodome pandas pyarrow

python run_scraper.py list      # فاز ۱: مناطق + لیست همه مدارس (۱۵۷۰ منطقه-جنسیت)
python run_scraper.py details   # فاز ۲: جزئیات/مجوز/تاریخچه هر مدرسه (۳ درخواست)
python run_scraper.py export    # فاز ۳: پاکسازی + ساخت CSV + Parquet نهایی
python run_scraper.py all       # هر سه فاز پشت‌سرهم

python clean_data.py            # پاکسازی مجددِ خروجی فعلی (بدون اسکرپ مجدد)
python validate_data.py         # اعتبارسنجی داده‌های استخراج‌شده
```

</div>

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

## 🌍 محدودیت دسترسی

> ⚠️ سامانه‌های `portal.mosharekatha.ir` و `my.mosharekatha.ir` از **خارج از ایران در دسترس نیستند**؛
> به همین دلیل استخراج داده را نمی‌توان داخل خودِ گیت‌هاب و GitHub Actions به‌صورت خودکار اجرا کرد.
> برای به‌روزرسانی داده، اسکریپت `python run_scraper.py` را از داخل ایران اجرا کنید و خروجی را
> با push در مخزن قرار دهید.

---

## 📌 نکته‌ها

- واحد پول: **ریال** (ستون‌های شهریه رشته‌ای‌اند؛ ستون `*_total` عددی).
- **مقطع (`stage`)** به‌صورت اسم فارسی است — نگاشت کد واقعیِ ردیف‌ها
  (فیلد `stage_type_id`) که با کدهای dropdown سایت (`2/3/16/17`) **فرق دارد**:

  <div dir="ltr">

  | کد ردیف | مقدار `stage` |
  |---|---|
  | `3` | ابتدایی |
  | `31` | ابتدایی استثنایی |
  | `5` | متوسطه دوره اول |
  | `11` | متوسطه دوره دوم شاخه نظری |
  | `12` | متوسطه دوره دوم شاخه فنی و حرفه‌ای |
  | `15` | متوسطه دوره دوم شاخه کاردانش |

  </div>

  (تأییدشده از badge صفحه جزئیات مدرسه و جدول خود داشبورد؛ فیلتر dropdown
  سایت عملاً اعمال نمی‌شود و اسکریپت با کدهای باز `0..99` همه مقاطع را می‌گیرد.
  کدهای نادر `31/90/92` (۱۰ مدرسه) هم از بج و مجوزِ خود سایت نگاشت شدند —
  توضیح کامل در [`metadata.md`](metadata.md).)
- `confirm_tuition`: `True` = شهریه تاییدشده (توکن‌های `1rdc58xq30.b1b` /
  `1rdc5g61nn.3e1` نرمال‌سازی شدند)، `False` = در انتظار تایید.
- `gender`: `1`=پسرانه، `2`=دخترانه.
- توضیح کامل ستون‌ها: [`metadata.md`](metadata.md)

---

**پیوندها:** [مخزن گیت‌هاب](https://github.com/IranOpenDataLab/Iran-Private-School-Fees) · [IranOpenDataLab](https://github.com/IranOpenDataLab)
