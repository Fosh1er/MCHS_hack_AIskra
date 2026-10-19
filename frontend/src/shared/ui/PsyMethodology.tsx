/** «Методика» психологического модификатора (F4, RF4-03): научно-методическая основа и профили заявителя карточками —
 *  признаки по шкале ECCS, что делать, что нельзя, источники. Всё из `GET /training/psy/methodology` (каталог
 *  `psy_profiles.yaml`), текста методики во фронте нет. Показывается у преподавателя и во вкладке справочной базы. */
import { useState } from 'react';
import { Banner, Card, Segmented, Tag } from '@smena112/ui-kit';
import { usePsyMethodology, type PsyProfileCard } from '../api/training';
import { PsyLevels } from './PsyBlock';
import { SourceRefs } from './PsySources';

function ProfileCard({ p }: { p: PsyProfileCard }) {
  const start = p.signs.find((s) => s.level === p.start);
  return (
    <Card title={p.title} subtitle={<>{p.group_title}{p.sensitive && <> · <Tag variant="dark">тяжёлая тема</Tag></>}</>}>
      <div className="mth-profile">
        <p className="mth-line">
          <PsyLevels level={p.start} /> Начинает с уровня {p.start} — {start?.title ?? ''}.{' '}
          {p.deescalates ? `Правильные действия снижают его до ${p.floor}.` : 'Не успокаивается: оценивается решение оператора.'}
        </p>
        <div className="mth-sect">Признаки</div>
        {start && <p className="mth-line">{start.text}</p>}
        <details className="tch-details">
          <summary>как звучит на других уровнях</summary>
          <dl className="tch-dl mth-levels">
            {p.signs.filter((s) => s.level !== p.start).map((s) => (
              <div key={s.level} style={{ display: 'contents' }}>
                <dt>{s.level} — {s.title}</dt><dd>{s.text}</dd>
              </div>
            ))}
          </dl>
        </details>
        <div className="mth-sect">Что делать <span className="psy-src">· жирным — ключевые приёмы</span></div>
        <ul className="mth-list">
          {p.does.map((a) => <li key={a.code}>{a.key ? <b>{a.title}</b> : a.title}</li>)}
        </ul>
        <div className="mth-sect">Что нельзя</div>
        <ul className="mth-list">
          {p.donts.map((a) => <li key={a.code}>{a.title}{a.critical && <> <Tag>не зачтено</Tag></>}</li>)}
        </ul>
        {p.routing.length > 0 && (
          <>
            <div className="mth-sect">Решение</div>
            <ul className="mth-list">{p.routing.map((r) => <li key={r}>{r}</li>)}</ul>
          </>
        )}
        <p className="mth-line mth-sources"><SourceRefs codes={p.sources} label="Источники" /></p>
      </div>
    </Card>
  );
}

export function PsyMethodologyView() {
  const q = usePsyMethodology();
  const [group, setGroup] = useState<string>('');
  const m = q.data;
  if (q.isError) return <Banner status="critical">{q.error.message}</Banner>;
  if (!m) return <Card title="Методика">загрузка…</Card>;
  const groups = [...new Map(m.profiles.map((p) => [p.group, p.group_title])).entries()];
  const list = m.profiles.filter((p) => !group || p.group === group);
  return (
    <>
      <Card title="Научно-методическая основа" subtitle={`${m.profiles.length} состояний заявителя · ${Object.keys(m.sources).length} источников`}>
        <p className="mth-line">
          Состояние заявителя ведёт движок по шкале ECCS, а не языковая модель. Правильные и запрещённые действия оператора
          взяты из официальных документов, у каждого правила — ссылка на источник.
        </p>
        <ul className="mth-basis">
          {m.basis.map((b) => (
            <li key={b.source.code}>
              {b.source.url ? <a href={b.source.url} target="_blank" rel="noreferrer">{b.source.title}</a> : b.source.title}
              <span className="c-slate"> — {b.use}</span>
            </li>
          ))}
        </ul>
        <div className="mth-sect">Шкала состояния заявителя ECCS</div>
        <div className="mth-scale">
          {m.scale.map((s) => <span key={s.level}><PsyLevels level={s.level} title={s.title} /> {s.level} — {s.title}</span>)}
        </div>
      </Card>
      <div className="cab-filters">
        <Segmented ariaLabel="Группа состояний" value={group} onChange={setGroup}
          options={[{ value: '', label: `все (${m.profiles.length})` }, ...groups.map(([g, t]) => ({ value: g, label: t.toLowerCase() }))]} />
      </div>
      <div className="mth-grid">
        {list.map((p) => <ProfileCard key={p.id} p={p} />)}
      </div>
    </>
  );
}
