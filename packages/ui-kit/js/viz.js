/* ==========================================================================
   СМЕНА-112 · viz.js — лёгкие графики для статичных страниц (без зависимостей).
   В React-приложении те же графики — компоненты <Sparkline/> и <LineChart/>
   (react/charts.tsx). Правила: одна ось Y, линия 2px, hairline-сетка,
   прицел + подсказка при наведении/фокусе, таблица-двойник у каждого графика,
   подписи вставляются только через textContent.
   ========================================================================== */
(function (root) {
  'use strict';
  var NS = 'http://www.w3.org/2000/svg';

  function el(tag, attrs, parent) {
    var n = document.createElementNS(NS, tag);
    for (var k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }
  function fmt(v) { return Math.round(v).toLocaleString('ru-RU'); }

  /** Спарклайн стат-плитки: история — приглушённым тоном, текущий отрезок — акцентом. */
  function sparkline(svg, values) {
    var w = 90, h = 24, pad = 3;
    svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
    svg.setAttribute('aria-hidden', 'true');
    svg.classList.add('spark');
    var min = Math.min.apply(null, values), max = Math.max.apply(null, values), span = (max - min) || 1;
    var x = function (i) { return pad + i * (w - 2 * pad) / (values.length - 1); };
    var y = function (v) { return h - pad - (v - min) / span * (h - 2 * pad); };
    var pts = values.map(function (v, i) { return x(i).toFixed(1) + ',' + y(v).toFixed(1); });
    el('polyline', { points: pts.slice(0, -1).join(' '), 'class': 'spark__line' }, svg);
    el('polyline', { points: pts.slice(-2).join(' '), 'class': 'spark__now' }, svg);
    var last = values.length - 1;
    el('circle', { cx: x(last), cy: y(values[last]), r: 2.5, 'class': 'spark__dot' }, svg);
  }

  /**
   * Линейный график одной серии с порогом.
   * opts: { points:[{t, v}], yMax, yStep, unit, seriesLabel, threshold:{value,label}, height, xEvery }
   */
  function lineChart(fig, opts) {
    var svg = fig.querySelector('.viz__svg');
    // Ширина viewBox = реальной ширине контейнера: подписи осей остаются 11px на любом экране
    var W = Math.max(320, Math.round(fig.clientWidth || 640)), H = opts.height || 220, m = { t: 12, r: 70, b: 26, l: 48 };
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    var iw = W - m.l - m.r, ih = H - m.t - m.b, pts = opts.points, n = pts.length;
    var x = function (i) { return m.l + i * iw / (n - 1); };
    var y = function (v) { return m.t + ih - Math.min(v, opts.yMax) / opts.yMax * ih; };

    for (var v = 0; v <= opts.yMax; v += opts.yStep) {
      el('line', { x1: m.l, x2: m.l + iw, y1: y(v), y2: y(v), 'class': v === 0 ? 'viz-axis' : 'viz-grid' }, svg);
      el('text', { x: m.l - 6, y: y(v) + 4, 'text-anchor': 'end', 'class': 'viz-tick' }, svg).textContent = fmt(v);
    }
    var every = opts.xEvery || Math.ceil(n / 6);
    pts.forEach(function (p, i) {
      if (i % every === 0 && i < n - every / 2) {
        el('text', { x: x(i), y: H - 6, 'text-anchor': i === 0 ? 'start' : 'middle', 'class': 'viz-tick' }, svg).textContent = p.t;
      }
    });
    el('text', { x: x(n - 1), y: H - 6, 'text-anchor': 'end', 'class': 'viz-tick' }, svg).textContent = pts[n - 1].t;

    if (opts.threshold) {
      var ty = y(opts.threshold.value);
      el('line', { x1: m.l, x2: m.l + iw, y1: ty, y2: ty, 'class': 'viz-threshold' }, svg);
      el('text', { x: m.l + iw + 6, y: ty + 4, 'class': 'viz-threshold-label' }, svg).textContent = opts.threshold.label;
    }

    var d = pts.map(function (p, i) { return (i ? 'L' : 'M') + x(i).toFixed(1) + ',' + y(p.v).toFixed(1); }).join('');
    el('path', { d: d + 'L' + x(n - 1) + ',' + y(0) + 'L' + x(0) + ',' + y(0) + 'Z', 'class': 'viz-area' }, svg);
    el('path', { d: d, 'class': 'viz-line' }, svg);
    var lastV = pts[n - 1].v;
    el('circle', { cx: x(n - 1), cy: y(lastV), r: 4, 'class': 'viz-end' }, svg);
    el('text', { x: x(n - 1) + 8, y: y(lastV) + 4, 'class': 'viz-end-label' }, svg).textContent = fmt(lastV) + ' ' + opts.unit;

    // Слой наведения: прицел находит X, подсказка показывает значение
    var cross = el('line', { y1: m.t, y2: m.t + ih, 'class': 'viz-cross', visibility: 'hidden' }, svg);
    var dot = el('circle', { r: 4, 'class': 'viz-end', visibility: 'hidden' }, svg);
    var hit = el('rect', { x: m.l, y: m.t, width: iw, height: ih, 'class': 'viz-hit', tabindex: 0, role: 'img',
      'aria-label': opts.seriesLabel + ': стрелками влево/вправо — значения по времени' }, svg);
    var tip = document.createElement('div');
    tip.className = 'viz-tip';
    tip.hidden = true;
    var tv = document.createElement('div'); tv.className = 'viz-tip__value';
    var key = document.createElement('span'); key.className = 'viz-tip__key';
    var tvText = document.createElement('span');
    tv.appendChild(key); tv.appendChild(tvText);
    var tl = document.createElement('div'); tl.className = 'viz-tip__label';
    tip.appendChild(tv); tip.appendChild(tl);
    fig.appendChild(tip);
    var cur = n - 1;

    function show(i) {
      cur = Math.max(0, Math.min(n - 1, i));
      var p = pts[cur];
      cross.setAttribute('x1', x(cur)); cross.setAttribute('x2', x(cur)); cross.setAttribute('visibility', 'visible');
      dot.setAttribute('cx', x(cur)); dot.setAttribute('cy', y(p.v)); dot.setAttribute('visibility', 'visible');
      tvText.textContent = fmt(p.v) + ' ' + opts.unit;
      tl.textContent = opts.seriesLabel + ' · ' + p.t;
      tip.hidden = false;
      var r = svg.getBoundingClientRect(), fr = fig.getBoundingClientRect();
      var px = r.left - fr.left + x(cur) * r.width / W, py = r.top - fr.top + y(p.v) * r.height / H;
      var left = px + 12;
      if (left + tip.offsetWidth > fr.width) left = px - tip.offsetWidth - 12;
      tip.style.left = left + 'px';
      tip.style.top = Math.max(0, py - tip.offsetHeight - 8) + 'px';
    }
    function hide() { cross.setAttribute('visibility', 'hidden'); dot.setAttribute('visibility', 'hidden'); tip.hidden = true; }
    hit.addEventListener('pointermove', function (e) {
      var r = svg.getBoundingClientRect();
      var sx = (e.clientX - r.left) * W / r.width;
      show(Math.round((sx - m.l) / iw * (n - 1)));
    });
    hit.addEventListener('pointerleave', hide);
    hit.addEventListener('focus', function () { show(cur); });
    hit.addEventListener('blur', hide);
    hit.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowLeft') { show(cur - 1); e.preventDefault(); }
      if (e.key === 'ArrowRight') { show(cur + 1); e.preventDefault(); }
    });

    // Таблица-двойник (доступный эквивалент графика)
    var holder = fig.querySelector('.viz-table');
    if (holder) {
      var table = document.createElement('table'); table.className = 'cab-table';
      var hr = table.insertRow(); ['Время', opts.seriesLabel].forEach(function (h, j) {
        var th = document.createElement('th'); th.textContent = h; if (j) th.className = 'num'; hr.appendChild(th);
      });
      pts.forEach(function (p) {
        var r = table.insertRow();
        r.insertCell().textContent = p.t;
        var c = r.insertCell(); c.className = 'num'; c.textContent = fmt(p.v) + ' ' + opts.unit;
      });
      holder.appendChild(table);
    }
    var card = fig.closest('.cab-card');
    var toggle = fig.querySelector('[data-viz-toggle]') || (card && card.querySelector('[data-viz-toggle]'));
    if (toggle) toggle.addEventListener('click', function () {
      var table = fig.getAttribute('data-view') !== 'table';
      fig.setAttribute('data-view', table ? 'table' : 'chart');
      toggle.setAttribute('aria-pressed', String(table));
      toggle.lastChild.textContent = table ? 'График' : 'Таблица';
    });
  }

  root.SmenaViz = { sparkline: sparkline, lineChart: lineChart };
})(window);
