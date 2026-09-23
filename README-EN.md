# 🏫 Non-governmental school data extraction — Tuition 1405-1406

🌐 **Persian version: [README.md](README.md)**

Full extraction of non-governmental (private) school data from
[`portal.mosharekatha.ir`](https://portal.mosharekatha.ir/dashboard/school-tuition) and
[`my.mosharekatha.ir`](https://my.mosharekatha.ir) — school link, profile, license,
ownership/location details and approved tuition / extra-curricular fees.

---

## 📊 Repository stats

<!-- STATS:START -->

<div dir="ltr">

| Indicator | Value |
|---|---:|
| 🏫 Total schools | **24,648** |
| 🗺️ Provinces | 32 |
| 📍 Education districts | 558 |
| 📚 Stage breakdown | Primary 13,768 · Primary (special needs) 8 · Lower secondary 5,780 · Upper secondary – theoretical 3,532 · Upper secondary – technical & vocational 919 · Upper secondary – Kardanesh 641 |
| 🧾 Tuition process status | Tuition announced 13,142 · Announced – pending confirmation 4,307 · Completed by founder 640 · Awaiting founder completion 373 · Approved by district expert 742 · Rejected by district expert 244 · Rejected by province expert 11 · No tuition request filed 5,189 |
| 📄 Schools with a license | 14,198 (57%) |
| 📊 Schools with tuition history | 20,988 (85%) |
| ✅ Confirmed tuition (1405) | 13,143 (53%) |
| 🕐 Last data update | `1405/07/01` — `2026-09-23 18:10` |
| 💾 Output sizes | CSV 17.7 MB / Parquet 10.3 MB |

</div>

<!-- STATS:END -->

---

## 📁 Project structure

| File / folder | Description |
|---|---|
| `scraper.py` | Core: response decryption + API functions (districts, school list, details, licenses, tuition history) |
| `run_scraper.py` | Three-phase, resumable runner: `list` → `details` → `export` |
| `clean_data.py` | Standalone cleaning of the current data (province/district names, confirmation boolean, stage/status labels, chronological tuition columns, `*_total` columns) |
| `validate_data.py` | Data validation: JSONL integrity, error rates, CSV/Parquet output sanity |
| `scripts/update_readme_stats.py` | Auto-generates the stats block of `README.md` and `README-EN.md` |
| `RELEASE_NOTES.md` | The "latest update notes" text published in the Release |
| `.github/workflows/update-stats.yml` | Action that refreshes both READMEs' stats on every push |
| `.github/workflows/release.yml` | Action that publishes `schools_data.csv` and `schools_data.parquet` to Releases on every push |
| `schools_data.csv` | **Final output** — 42 cleaned columns, UTF-8-BOM (Excel-friendly) |
| `schools_data.parquet` | Same output + `raw_detail` / `raw_licenses` / `raw_tuition_history` (stringified JSON) |
| `metadata.md` | Full column documentation + field sources + code decoding (Persian) |
| `checkpoint/` | Resume checkpoints (continue after interruptions) |
| `scraper_log.txt` | Full run log |

---

## 🚀 How to run

```bash
pip install requests pycryptodome pandas pyarrow

python run_scraper.py list      # Phase 1: districts + full school list (1,570 district-gender combos)
python run_scraper.py details   # Phase 2: details/licenses/tuition history per school (3 requests)
python run_scraper.py export    # Phase 3: cleaning + final CSV/Parquet build
python run_scraper.py all       # all three phases in sequence

python clean_data.py            # re-clean the current output (no re-scrape)
python validate_data.py         # validate the extracted data
```

- **Resumable:** each phase saves to `checkpoint/`; re-running continues from there.
- **Rate limiting:** `LIST_SLEEP` / `DETAIL_SLEEP` constants at the top of `run_scraper.py`.

---

## 🔌 System API (summary)

- endpoint: `POST {domain}/core-api/v1/data-provider/get-data-source`
- body: `{serviceId, key, params}` — response: `{"token": "<base64>"}`, decrypted with
  AES-256-CBC (OpenSSL `Salted__` format, key derived via `EvpBytesToKey` with MD5).
- no `client-id` header; the server falls back to a default key.
- data keys (`key`):
  - `medungo-explore/get/sub-organs` — provinces/districts (`organPath`)
  - `mosharekatha-portal/load/school-tuition-inquiry` — school list (`regionPath`, `gender`, `stage_id`, `year`, `limit`, `page`, `filters`)
  - `my-mosharekatha/school-panel/school-detail/load` — school details
  - `my-mosharekatha/school-panel/school-licenses/load` — licenses
  - `my-mosharekatha/school-panel/school-tuition-history/load` — tuition history (1403/1404/1405)
- national licenses gateway link: `https://qr.mojavez.ir/track/{RequestNumber}`

---

## 🌐 Access & publishing

- **Access limitation:** the [`portal.mosharekatha.ir`](https://portal.mosharekatha.ir/dashboard/school-tuition) and [`my.mosharekatha.ir`](https://my.mosharekatha.ir) portals are **not accessible from outside Iran**; since GitHub Actions runners execute outside Iran, **the scraping cannot be automated inside GitHub itself** — `python run_scraper.py` must be run manually from inside Iran, and the output is then pushed to the repository.
- **Release publishing:** on every push, the [`.github/workflows/release.yml`](.github/workflows/release.yml) action uploads `schools_data.csv` and `schools_data.parquet` to the repository's [Releases](https://github.com/IranOpenDataLab/Iran-Private-School-Fees/releases) page together with the update date (Solar Hijri and Gregorian) and the "latest update notes" from [`RELEASE_NOTES.md`](RELEASE_NOTES.md).

---

## 📌 Notes

- Currency: **Rial** (tuition value columns are strings; `*_total` columns are numeric).
- **Stage (`stage`)** is written as a name — mapping of the real row codes
  (`stage_type_id`), which differ from the site's dropdown codes (`2/3/16/17`):

  | Row code | `stage` value |
  |---|---|
  | `3` | Primary (ابتدایی) |
  | `31` | Primary – special needs (ابتدایی استثنایی) |
  | `5` | Lower secondary (متوسطه دوره اول) |
  | `11` | Upper secondary – theoretical (متوسطه دوره دوم شاخه نظری) |
  | `12` | Upper secondary – technical & vocational (متوسطه دوره دوم شاخه فنی و حرفه‌ای) |
  | `15` | Upper secondary – Kardanesh (متوسطه دوره دوم شاخه کاردانش) |

  (Verified from the badge on the school detail page and the dashboard table itself; the
  site's dropdown filter is effectively not applied and the script requests the open range
  `0..99` to cover every stage. Rare codes `31/90/92` (10 schools) were mapped from the
  site's own badge/license — full details in [`metadata.md`](metadata.md).)
- `confirm_tuition`: `True` = confirmed tuition (backend tokens `1rdc58xq30.b1b` /
  `1rdc5g61nn.3e1` normalized), `False` = pending confirmation.
- `gender`: `1` = boys, `2` = girls.
- Full column documentation: [`metadata.md`](metadata.md) (Persian).

---

## 🔗 Links

- Repository: [IranOpenDataLab/Iran-Private-School-Fees](https://github.com/IranOpenDataLab/Iran-Private-School-Fees)
- Organization: [IranOpenDataLab](https://github.com/IranOpenDataLab)
