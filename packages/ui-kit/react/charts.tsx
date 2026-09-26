/* Графики по правилам dataviz: одна ось Y, линия 2px, hairline-сетка, прицел + подсказка
   на наведение и фокус, таблица-двойник. Геометрия совпадает с js/viz.js (HTML-превью). */
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';
import { Icon } from './Icon';

const fmt = (v: number) => Math.round(v).toLocaleString('ru-RU');

/* ---------- Sparkline: история приглушённым тоном, текущий отрезок — акцентом ---------- */
export function Sparkline({ values, width = 90, height = 24 }: { values: number[]; width?: number; height?: number }) {
  const pad = 3;
  const { pts, last } = useMemo(() => {
    const min = Math.min(...values), max = Math.max(...values), span = max - min || 1;
    const p = values.map((v, i) => [
      pad + (i * (width - 2 * pad)) / (values.length - 1),
      height - pad - ((v - min) / span) * (height - 2 * pad),
    ] as const);
    return { pts: p, last: p[p.length - 1] };
  }, [values, width, height]);
  const toStr = (arr: readonly (readonly [number, number])[]) => arr.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  return (
    <svg className="spark" viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
      <polyline className="spark__line" points={toStr(pts.slice(0, -1))} />
      <polyline className="spark__now" points={toStr(pts.slice(-2))} />
      <circle className="spark__dot" cx={last[0]} cy={last[1]} r={2.5} />
    </svg>
  );
}

/* ---------- LineChart: одна серия + порог ---------- */
export interface LinePoint { t: string; v: number; }
export interface LineChartProps {
  points: LinePoint[];
  yMax: number;
  yStep: number;
  unit: string;
  seriesLabel: string;
  threshold?: { value: number; label: string };
  height?: number;
  xEvery?: number;
}
export function LineChart({ points, yMax, yStep, unit, seriesLabel, threshold, height = 220, xEvery }: LineChartProps) {
  const figRef = useRef<HTMLElement>(null);
  // Ширина viewBox = реальной ширине контейнера: подписи осей остаются 11px на любом экране
  const [W, setW] = useState(640);
  useEffect(() => {
    const el = figRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(([entry]) => setW(Math.max(320, Math.round(entry.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const H = height, m = { t: 12, r: 70, b: 26, l: 48 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b, n = points.length;
  const x = (i: number) => m.l + (i * iw) / (n - 1);
  const y = (v: number) => m.t + ih - (Math.min(v, yMax) / yMax) * ih;
  const every = xEvery ?? Math.ceil(n / 6);
  const [view, setView] = useState<'chart' | 'table'>('chart');
  const [hover, setHover] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const tableId = useId();

  const d = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.v).toFixed(1)}`).join('');
  const ticks: number[] = [];
  for (let v = 0; v <= yMax; v += yStep) ticks.push(v);
  const lastV = points[n - 1].v;

  const onMove = (e: PointerEvent<SVGRectElement>) => {
    const r = svgRef.current!.getBoundingClientRect();
    const sx = ((e.clientX - r.left) * W) / r.width;
    setHover(Math.max(0, Math.min(n - 1, Math.round(((sx - m.l) / iw) * (n - 1)))));
  };
  const onKey = (e: KeyboardEvent<SVGRectElement>) => {
    if (e.key === 'ArrowLeft') { setHover((h) => Math.max(0, (h ?? n - 1) - 1)); e.preventDefault(); }
    if (e.key === 'ArrowRight') { setHover((h) => Math.min(n - 1, (h ?? n - 1) + 1)); e.preventDefault(); }
  };

  // Позиция подсказки в координатах figure
  let tip: { left: number; top: number } | null = null;
  if (hover != null && svgRef.current && figRef.current) {
    const r = svgRef.current.getBoundingClientRect(), fr = figRef.current.getBoundingClientRect();
    const px = r.left - fr.left + (x(hover) * r.width) / W, py = r.top - fr.top + (y(points[hover].v) * r.height) / H;
    tip = { left: px + 150 > fr.width ? px - 150 : px + 12, top: Math.max(0, py - 52) };
  }

  return (
    <figure className="viz" ref={figRef} data-view={view}>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 4 }}>
        <button type="button" className="cab-btn cab-btn--sm" aria-pressed={view === 'table'} aria-controls={tableId}
          onClick={() => setView(view === 'chart' ? 'table' : 'chart')}>
          <Icon name={view === 'chart' ? 'table' : 'bar_chart'} size="sm" />{view === 'chart' ? 'Таблица' : 'График'}
        </button>
      </div>
      <svg ref={svgRef} className="viz__svg" viewBox={`0 0 ${W} ${H}`} role="presentation">
        {ticks.map((v) => (
          <g key={v}>
            <line className={v === 0 ? 'viz-axis' : 'viz-grid'} x1={m.l} x2={m.l + iw} y1={y(v)} y2={y(v)} />
            <text className="viz-tick" x={m.l - 6} y={y(v) + 4} textAnchor="end">{fmt(v)}</text>
          </g>
        ))}
        {points.map((p, i) => (i % every === 0 && i < n - every / 2 ? (
          <text key={p.t} className="viz-tick" x={x(i)} y={H - 6} textAnchor={i === 0 ? 'start' : 'middle'}>{p.t}</text>
        ) : null))}
        <text className="viz-tick" x={x(n - 1)} y={H - 6} textAnchor="end">{points[n - 1].t}</text>
        {threshold && (
          <>
            <line className="viz-threshold" x1={m.l} x2={m.l + iw} y1={y(threshold.value)} y2={y(threshold.value)} />
            <text className="viz-threshold-label" x={m.l + iw + 6} y={y(threshold.value) + 4}>{threshold.label}</text>
          </>
        )}
        <path className="viz-area" d={`${d}L${x(n - 1)},${y(0)}L${x(0)},${y(0)}Z`} />
        <path className="viz-line" d={d} />
        <circle className="viz-end" cx={x(n - 1)} cy={y(lastV)} r={4} />
        <text className="viz-end-label" x={x(n - 1) + 8} y={y(lastV) + 4}>{fmt(lastV)} {unit}</text>
        {hover != null && (
          <>
            <line className="viz-cross" x1={x(hover)} x2={x(hover)} y1={m.t} y2={m.t + ih} />
            <circle className="viz-end" cx={x(hover)} cy={y(points[hover].v)} r={4} />
          </>
        )}
        <rect className="viz-hit" x={m.l} y={m.t} width={iw} height={ih} tabIndex={0} role="img"
          aria-label={`${seriesLabel}: стрелками влево/вправо — значения по времени`}
          onPointerMove={onMove} onPointerLeave={() => setHover(null)}
          onFocus={() => setHover(n - 1)} onBlur={() => setHover(null)} onKeyDown={onKey} />
      </svg>
      {hover != null && tip && (
        <div className="viz-tip" style={{ left: tip.left, top: tip.top }}>
          <div className="viz-tip__value"><span className="viz-tip__key" />{fmt(points[hover].v)} {unit}</div>
          <div className="viz-tip__label">{seriesLabel} · {points[hover].t}</div>
        </div>
      )}
      <div className="viz-table" id={tableId}>
        <table className="cab-table">
          <thead><tr><th>Время</th><th className="num">{seriesLabel}</th></tr></thead>
          <tbody>{points.map((p) => <tr key={p.t}><td>{p.t}</td><td className="num">{fmt(p.v)} {unit}</td></tr>)}</tbody>
        </table>
      </div>
    </figure>
  );
}
