/* Shared helpers: FA numbers, Arabic/FA unification, modal, CSV download. */
(function () {
  'use strict';
  const FA_D = '۰۱۲۳۴۵۶۷۸۹';

  function faNum(x) {
    if (x === null || x === undefined || x === '') return '—';
    if (typeof x === 'number' && Number.isInteger(x)) {
      return x.toString().replace(/\B(?=(\d{3})+(?!\d))/g, '٬')
        .replace(/[0-9]/g, (d) => FA_D[+d]);
    }
    if (typeof x === 'number') return faNum(Math.round(x));
    return String(x).replace(/[0-9]/g, (d) => FA_D[+d]);
  }

  // Same unification as build_dashboard_data.py (index + query must match).
  function normFa(s) {
    return (s || '').replace(/[ي]/g, 'ی').replace(/[ك]/g, 'ک')
      .replace(/[ة]/g, 'ه').replace(/[ؤ]/g, 'و')
      .replace(/[إأآ]/g, 'ا').replace(/[۰-۹]/g, (d) => '0123456789'['۰۱۲۳۴۵۶۷۸۹'.indexOf(d)])
      .replace(/[_\-–—"«»()[\]{},.:;،؛؟!*+=~/\\|<>`^#@&×÷]/g, ' ')
      .replace(/\s+/g, ' ').trim().toLowerCase();
  }

  function debounce(fn, ms) {
    let t = 0;
    return function (...a) { clearTimeout(t); t = setTimeout(() => fn.apply(this, a), ms); };
  }

  async function getJSON(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error('fetch failed: ' + url);
    return r.json();
  }

  function moneyRows(p, y) {
    const t = p[y + '_tuition'] ?? p.tu ?? null;
    const e = p[y + '_extra'] ?? p.ex ?? null;
    const tot = p[y + '_total'] ?? p.t ?? null;
    return { t, e, tot };
  }

  function openModal(html) {
    closeModal();
    const m = document.createElement('div');
    m.className = 'modal'; m.id = 'dshModal';
    m.innerHTML = '<div class="box">' + html +
      '<p style="text-align:left"><button class="ghost" id="dshClose">بستن</button></p></div>';
    m.addEventListener('click', (ev) => {
      if (ev.target === m || ev.target.id === 'dshClose') closeModal();
    });
    document.addEventListener('keydown', escClose);
    document.body.appendChild(m);
  }
  function escClose(ev) { if (ev.key === 'Escape') closeModal(); }
  function closeModal() {
    const m = document.getElementById('dshModal');
    if (m) m.remove();
    document.removeEventListener('keydown', escClose);
  }

  function schoolURL(p) {
    if (p.school_url) return p.school_url;
    if (p.p) return 'https://my.mosharekatha.ir/school-details/' + p.p;
    return null;
  }

  function profileHTML(p) {
    const url = schoolURL(p);
    const y = 1404;
    const m = moneyRows(p, y);
    let h = '<h3 style="margin-top:0">' + (p.school_name || p.n || '') + '</h3><dl class="kv">';
    if (p.school_id || p.id) h += '<dt>کد مدرسه</dt><dd>' + (p.school_id || p.id) + '</dd>';
    if (p.province || p.ps) h += '<dt>استان</dt><dd>' + (p.province || p.ps) + '</dd>';
    if (p.district || p.d) h += '<dt>ناحیه</dt><dd>' + (p.district || p.d) + '</dd>';
    if (p.stage || p.s) h += '<dt>مقطع</dt><dd>' + (p.stage || p.s) + '</dd>';
    if (p.gender || p.g) h += '<dt>جنسیت</dt><dd>' + (p.gender || p.g) + '</dd>';
    if (p.founder) h += '<dt>موسس</dt><dd>' + p.founder + '</dd>';
    if (p.license_holder) h += '<dt>مجوزدهنده</dt><dd>' + p.license_holder + '</dd>';
    if (p.process_status_label) h += '<dt>وضعیت</dt><dd>' + p.process_status_label + '</dd>';
    h += '</dl><div class="money"><div><span>شهریه مصوب ۱۴۰۴</span><b>' +
      faNum(m.t) + ' ریال</b></div><div><span>فوق‌برنامه ۱۴۰۴</span><b>' +
      faNum(m.e) + ' ریال</b></div><div><span>مجموع ۱۴۰۴</span><b>' +
      faNum(m.tot) + ' ریال</b></div></div>';
    if (url) h += '<p><a href="' + url + '" target="_blank" rel="noopener">صفحه مدرسه در سامانه ⬈</a></p>';
    return h;
  }

  function downloadCSV(filename, rows) {
    const head = Object.keys(rows[0] || {});
    const q = (v) => '"' + String(v ?? '').replace(/"/g, '""') + '"';
    const csv = '﻿' + head.join(',') + '\n' +
      rows.map((r) => head.map((k) => q(r[k])).join(',')).join('\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    a.download = filename;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  }

  window.DSH = { faNum, normFa, debounce, getJSON, openModal, closeModal, profileHTML, downloadCSV, schoolURL };
})();
