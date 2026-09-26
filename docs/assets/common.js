/* Shared helpers: FA numbers, Arabic/FA unification, modal+history, CSV. */
(function () {
  'use strict';
  const FA_D = '۰۱۲۳۴۵۶۷۸۹';
  const FONT = 'Vazirmatn,Tahoma,sans-serif';

  function faNum(x) {
    if (x === null || x === undefined || x === '') return '—';
    if (typeof x === 'number' && Number.isInteger(x)) {
      return x.toString().replace(/\B(?=(\d{3})+(?!\d))/g, '٬')
        .replace(/[0-9]/g, (d) => FA_D[+d]);
    }
    if (typeof x === 'number') return faNum(Math.round(x));
    return String(x).replace(/[0-9]/g, (d) => FA_D[+d]);
  }

  function faYear(y) {
    return String(y || '').replace(/[0-9]/g, (d) => FA_D[+d]);
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

  async function fetchProgress(url, onPct) {
    const r = await fetch(url);
    if (!r.ok) throw new Error('fetch failed: ' + url);
    const total = +r.headers.get('content-length') || 0;
    if (!r.body || !r.body.getReader) {
      const j = await r.json();
      if (onPct) onPct(100);
      return j;
    }
    const rd = r.body.getReader();
    const chunks = [];
    let got = 0;
    for (;;) {
      const { done, value } = await rd.read();
      if (done) break;
      chunks.push(value);
      got += value.length;
      if (onPct && total) onPct(Math.min(99, Math.round((got / total) * 100)));
    }
    const buf = new Uint8Array(got);
    let off = 0;
    chunks.forEach((c) => { buf.set(c, off); off += c.length; });
    if (onPct) onPct(100);
    return JSON.parse(new TextDecoder('utf-8').decode(buf));
  }

  async function getJSON(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error('fetch failed: ' + url);
    return r.json();
  }

  function pick(o, ...keys) {
    for (const k of keys) if (o[k] !== undefined && o[k] !== null && o[k] !== '') return o[k];
    return null;
  }

  function schoolName(p) { return pick(p, 'school_name', 'n') || ''; }
  function schoolId(p) { return pick(p, 'school_id', 'id') || ''; }
  function schoolURL(p) {
    if (p.school_url) return p.school_url;
    const sp = pick(p, 'school_path', 'p');
    return sp ? 'https://my.mosharekatha.ir/school-details/' + sp : null;
  }

  function yearTag(y) {
    return y === 1405 ? '' : ' <small>(' + faYear(y || '—') + ')</small>';
  }

  function moneyLine(label, triple, year) {
    if (!triple) return '';
    return '<div><span>' + label + yearTag(year) + '</span><b>' +
      faNum(triple[0]) + ' ریال</b></div>' +
      '<div class="sub2"><span>مصوب / فوق‌برنامه</span><span>' +
      faNum(triple[1]) + ' / ' + faNum(triple[2]) + '</span></div>';
  }

  function profileHTML(p) {
    const url = schoolURL(p);
    let h = '<h3 style="margin-top:0">' + schoolName(p) + '</h3><dl class="kv">';
    const id = schoolId(p);
    if (id) h += '<dt>کد مدرسه</dt><dd>' + id + '</dd>';
    const prov = pick(p, 'province', 'ps');
    if (prov) h += '<dt>استان</dt><dd>' + prov + '</dd>';
    const dist = pick(p, 'district', 'd');
    if (dist) h += '<dt>ناحیه</dt><dd>' + dist + '</dd>';
    const st = pick(p, 'stage', 's');
    if (st) h += '<dt>مقطع</dt><dd>' + st + '</dd>';
    const g = pick(p, 'gender', 'g');
    if (g) h += '<dt>جنسیت</dt><dd>' + g + '</dd>';
    if (p.founder) h += '<dt>موسس</dt><dd>' + p.founder + '</dd>';
    if (p.license_holder) h += '<dt>مجوزدهنده</dt><dd>' + p.license_holder + '</dd>';
    if (p.process_status_label) h += '<dt>وضعیت</dt><dd>' + p.process_status_label + '</dd>';
    h += '</dl>';
    // primary: display-year total, then archive rows
    const dt = p.dt !== undefined ? p.dt : pick(p, '1405_total', '1404_total');
    const dy = p.dy !== undefined ? p.dy : (p.dt !== undefined ? null : null);
    h += '<div class="money"><div><span>مجموع نمایشی' + yearTag(dy === null ? 1405 : dy) +
      '</span><b>' + faNum(dt) + ' ریال</b></div></div>';
    if (p.y5 || p.y4 || p.y3) {
      h += '<div class="money">' +
        moneyLine('مجموع ۱۴۰۵', p.y5, 1405) +
        moneyLine('مجموع ۱۴۰۴', p.y4, 1404) +
        moneyLine('مجموع ۱۴۰۳', p.y3, 1403) + '</div>';
      if (p.fin) h += '<p class="legend">شهریه نهایی‌شده ۱۴۰۵: ' + p.fin + '</p>';
      h += '<div id="dshHist" class="chart sm"></div>';
    } else {
      // legacy full-profile rows (top.json always has y-triples now; kept for safety)
      ['1405', '1404', '1403'].forEach((y) => {
        if (p[y + '_total'] != null) {
          h += '<div class="money"><div><span>مجموع ' + faYear(y) + '</span><b>' +
            faNum(p[y + '_total']) + ' ریال</b></div></div>';
        }
      });
    }
    if (url) h += '<p><a href="' + url + '" target="_blank" rel="noopener">صفحه مدرسه در سامانه ⬈</a></p>';
    return h;
  }

  function drawHistory(p) {
    const el = document.getElementById('dshHist');
    if (!el || typeof echarts === 'undefined') return;
    const rows = [['۱۴۰۳', p.y3], ['۱۴۰۴', p.y4], ['۱۴۰۵', p.y5]]
      .filter(([, t]) => t && t[0] != null);
    if (rows.length < 2) { el.remove(); return; }
    const c = echarts.init(el);
    c.setOption({
      textStyle: { fontFamily: FONT },
      tooltip: { trigger: 'axis', valueFormatter: (v) => faNum(v) + ' ریال' },
      xAxis: { type: 'category', data: rows.map((r) => r[0]) },
      yAxis: { type: 'value', axisLabel: { formatter: (v) => faNum(v) } },
      series: [
        { name: 'مجموع', type: 'line', smooth: true, data: rows.map((r) => r[1][0]), itemStyle: { color: '#1a7f5a' } },
        { name: 'مصوب', type: 'line', smooth: true, data: rows.map((r) => r[1][1]), itemStyle: { color: '#457b9d' } },
        { name: 'فوق‌برنامه', type: 'line', smooth: true, data: rows.map((r) => r[1][2]), itemStyle: { color: '#e76f51' } },
      ],
      grid: { containLabel: true }, legend: { bottom: 0 },
    });
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
  function profileModal(p) {
    openModal(profileHTML(p));
    drawHistory(p);
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

  window.DSH = {
    faNum, faYear, normFa, debounce, getJSON, fetchProgress,
    openModal, closeModal, profileHTML, profileModal, schoolURL, FONT,
  };
})();
