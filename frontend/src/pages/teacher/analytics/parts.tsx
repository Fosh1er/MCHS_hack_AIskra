/** Общие элементы аналитики преподавателя (specs/4.5): «норматив / факт», доля в нормативе, типичные ошибки. */
import { Card, StatTile } from '@smena112/ui-kit';
import type { ErrorRow, NormStat } from '../../../shared/api/assessment';
import { num, plural } from '../../../shared/format';

export const pct = (x: number | null | undefined) => (x === null || x === undefined ? '—' : `${Math.round(x * 100)} %`);
export const sec = (x: number | null | undefined) => (x === null || x === undefined ? '—' : `${num(x)} с`);
export const roleLabel = (role: string, service?: string | null) => (role === '112' ? 'оператор 112' : `ДДС ${service ?? ''}`.trim());

/** Полоса доли в нормативе: красная ниже 70 %, жёлтая до 90 %. */
export function Share({ value }: { value: number | null }) {
  if (value === null) return <span className="c-slate">—</span>;
  const cls = value < 0.7 ? 'is-low' : value < 0.9 ? 'is-mid' : '';
  return (
    <span className="tch-share" title={`в нормативе ${pct(value)}`}>
      <span className="tch-share__track"><span className={`tch-share__fill ${cls}`} style={{ width: `${value * 100}%` }} /></span>
      {pct(value)}
    </span>
  );
}

/** Плитки «норматив / факт» по одному показателю. */
export function NormTiles({ label, stat }: { label: string; stat: NormStat }) {
  return (
    <section className="cab-kpis">
      <StatTile label={`${label}: в нормативе`} value={pct(stat.within_share)} note={stat.count ? `${stat.within} из ${stat.count}` : 'нет данных'} />
      <StatTile label="Норматив" value={sec(stat.norm_s)} />
      <StatTile label="Медиана" value={sec(stat.median_s)} />
      <StatTile label="90-й процентиль" value={sec(stat.p90_s)} note="9 из 10 уложились в это время" />
    </section>
  );
}

export function ErrorsCard({ title, rows, empty }: { title: string; rows: ErrorRow[]; empty: string }) {
  return (
    <Card title={title} subtitle="Замечание автооценки · сколько раз · карточки-примеры">
      {rows.length ? (
        <ol className="tch-list">
          {rows.map((e) => (
            <li key={e.text}>
              <b>{e.text}</b> — {e.count} {plural(e.count, 'раз', 'раза', 'раз')}
              <small>карточки № {e.cards.join(', ')}{e.students.length > 1 ? ` · ${e.students.join(', ')}` : ''}</small>
            </li>
          ))}
        </ol>
      ) : <p className="c-slate">{empty}</p>}
    </Card>
  );
}

/** Подпись точки графика: дата и время — несколько карточек за один день не сливаются. */
export const when = (iso: string) =>
  new Date(iso).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
