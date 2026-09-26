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

  // Display with Cache API: same-origin JSON is cached once (versioned name),
  // so refreshes don't re-download the graph/search payloads.
  const CACHE_NAME = 'dsh-cache-v2';

  async function fetchCached(url, onPct) {
    const done = (p) => { if (onPct) { try { onPct(p); } catch (_) {} } };
    try {
      if ('caches' in window) {
        const cache = await caches.open(CACHE_NAME);
        const hit = await cache.match(url);
        if (hit) { done(100); return hit.json(); }
      }
    } catch (_) { /* storage unavailable -> plain network */ }
    const r = await fetch(url);
    if (!r.ok) throw new Error('fetch failed: ' + url);
    const total = +r.headers.get('content-length') || 0;
    if (!r.body || !r.body.getReader) {
      const j = await r.json();
      done(100);
      return j;
    }
    const rd = r.body.getReader();
    const chunks = [];
    let got = 0;
    for (;;) {
      const part = await rd.read();
      if (part.done) break;
      chunks.push(part.value);
      got += part.value.length;
      if (total) done(Math.min(99, Math.round((got / total) * 100)));
    }
    const buf = new Uint8Array(got);
    let off = 0;
    chunks.forEach((c) => { buf.set(c, off); off += c.length; });
    done(100);
    try {
      if ('caches' in window) {
        const cache = await caches.open(CACHE_NAME);
        cache.put(url, new Response(buf.slice(), { headers: { 'Content-Type': 'application/json' } }));
      }
    } catch (_) { /* ignore quota errors */ }
    return JSON.parse(new TextDecoder('utf-8').decode(buf));
  }

  async function fetchProgress(url, onPct) {
    return fetchCached(url, onPct);
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
      faNum(triple[0]) + ' تومان</b></div>' +
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
    const dy = p.dy !== undefined ? p.dy : null;
    h += '<div class="money"><div><span>آخرین شهریه ثبت‌شده' + yearTag(dy === null ? 1405 : dy) +
      '</span><b>' + faNum(dt) + ' تومان</b></div></div>';
    if (p.y5 || p.y4 || p.y3) {
      h += '<div class="money">' +
        moneyLine('مجموع ۱۴۰۵', p.y5, 1405) +
        moneyLine('مجموع ۱۴۰۴', p.y4, 1404) +
        moneyLine('مجموع ۱۴۰۳', p.y3, 1403) + '</div>';
      h += '<div id="dshHist" class="chart sm"></div>';
    } else {
      // legacy full-profile rows (top.json always has y-triples now; kept for safety)
      ['1405', '1404', '1403'].forEach((y) => {
        if (p[y + '_total'] != null) {
          h += '<div class="money"><div><span>مجموع ' + faYear(y) + '</span><b>' +
            faNum(p[y + '_total']) + ' تومان</b></div></div>';
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
      tooltip: { trigger: 'axis', valueFormatter: (v) => faNum(v) + ' تومان' },
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
    if (window._dshFull) {
      try { window._dshFull.dispose(); } catch (_) {}
      window._dshFull = null;
    }
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

  // ---- chart registry: PNG export (with copyright footer) + fullscreen ----
  const REG = {};

  function registerChart(id, chart, option) {
    REG[id] = { chart, option };
  }

  function loadImage(src, timeoutMs, cors) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      const to = setTimeout(() => reject(new Error('img timeout')), timeoutMs || 4000);
      img.onload = () => { clearTimeout(to); resolve(img); };
      img.onerror = () => { clearTimeout(to); reject(new Error('img error')); };
      if (cors) img.crossOrigin = 'anonymous';
      img.src = src;
    });
  }

  async function exportPNG(id) {
    const R = REG[id];
    if (!R) return;
    const url = R.chart.getDataURL({ pixelRatio: 2, backgroundColor: '#ffffff' });
    const img = await loadImage(url, 8000, false);
    const footH = Math.max(56, Math.round(img.width * 0.055));
    const cv = document.createElement('canvas');
    cv.width = img.width;
    cv.height = img.height + footH;
    const ctx = cv.getContext('2d');
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, cv.width, cv.height);
    ctx.drawImage(img, 0, 0);
    ctx.strokeStyle = '#1a7f5a';
    ctx.lineWidth = Math.max(2, img.width / 600);
    ctx.beginPath();
    ctx.moveTo(0, img.height + 1);
    ctx.lineTo(cv.width, img.height + 1);
    ctx.stroke();
    const fs = Math.round(footH * 0.34);
    try {
      await document.fonts.load(fs + 'px Vazirmatn');
    } catch (_) {}
    const label = 'IranOpenDataLab  •  github.com/IranOpenDataLab';
    ctx.font = fs + 'px Vazirmatn, Tahoma, sans-serif';
    ctx.fillStyle = '#0f5c40';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const cy = img.height + footH / 2;
    try {
      const icon = await loadImage(
        'https://cdn.jsdelivr.net/npm/simple-icons/icons/github.svg', 2500, true);
      const s = footH * 0.4;
      const tw = ctx.measureText(label).width;
      ctx.drawImage(icon, cv.width / 2 - tw / 2 - s - 10, cy - s / 2, s, s);
      ctx.fillText(label, cv.width / 2 + (s + 10) / 2 - 4, cy);
    } catch (_) {
      ctx.fillText(label, cv.width / 2, cy);
    }
    const a = document.createElement('a');
    a.download = 'dsh-' + id + '.png';
    a.href = cv.toDataURL('image/png');
    a.click();
  }

  function fullscreenChart(id) {
    const R = REG[id];
    if (!R || typeof echarts === 'undefined') return;
    openModal('<div id="dshFull" style="width:100%;height:70vh"></div>');
    const c = echarts.init(document.getElementById('dshFull'));
    // live option (getOption) carries current data/zoom; falls back to registered
    let opt = null;
    try { opt = R.chart.getOption(); } catch (_) {}
    c.setOption(opt || R.option);
    c.resize();
    window._dshFull = c;
  }

  document.addEventListener('click', (ev) => {
    const p = ev.target.closest('[data-png]');
    if (p) { exportPNG(p.getAttribute('data-png')); return; }
    const f = ev.target.closest('[data-full]');
    if (f) { fullscreenChart(f.getAttribute('data-full')); }
  });

  window.DSH = {
    faNum, faYear, normFa, debounce, getJSON, fetchProgress, fetchCached,
    openModal, closeModal, profileHTML, profileModal, schoolURL, FONT,
    registerChart, exportPNG, fullscreenChart, downloadCSV,
  };
})();
