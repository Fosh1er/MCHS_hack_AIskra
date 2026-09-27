/** Разбор занятия (specs/4.5; ГОСТ Р 22.7.01, п. 3.12.3 — подведение итогов с разбором характерных недостатков,
 *  ≈ 10 мин): одна страница для экрана или печати — главные ошибки группы, что повторить, сверх норматива, лучшие. */
import { Link, useParams } from 'react-router-dom';
import { Banner, Button, Card, StatTile } from '@smena112/ui-kit';
import { useDebrief } from '../../../shared/api/assessment';
import { TeacherShell } from '../../../shared/ui/TeacherShell';
import { num } from '../../../shared/format';
import { ErrorsCard, pct, roleLabel } from './parts';

export function SessionDebriefPage() {
  const { id = '' } = useParams();
  const q = useDebrief(id);
  const d = q.data;
  return (
    <TeacherShell active="sessions" crumbs="Пульт / Занятия / Разбор" title={d ? `Разбор: ${d.title}` : 'Разбор занятия'}
      subtitle={d?.started_at ? new Date(d.started_at).toLocaleString('ru-RU') : undefined}
      actions={<span className="tch-noprint cab-filters">
        <Link className="cab-btn" to={`/teacher/sessions/${id}/report`}>отчёт</Link>
        <Button icon="description" onClick={() => window.print()}>печать</Button>
      </span>}>
      {q.isError && <Banner status="critical">{q.error.message}</Banner>}
      {d && (
        <>
          {d.assessed < d.cards && (
            <Banner>Оценено {d.assessed} из {d.cards}. Чтобы разбор был полным, в отчёте нажмите «оценить все карточки».</Banner>
          )}
          <section className="cab-kpis">
            <StatTile label="Средний балл" value={num(d.avg_score)} />
            <StatTile label="Зачтено" value={pct(d.passed_share)} />
            <StatTile label="112 в нормативе" value={pct(d.card_112.within_share)} note={d.card_112.count ? `медиана ${num(d.card_112.median_s)} с · норматив ${d.card_112.norm_s} с` : 'нет карточек'} />
            <StatTile label="ДДС в нормативе" value={pct(d.dds.within_share)} note={d.dds.count ? `медиана ${num(d.dds.median_s)} с · норматив ${d.dds.norm_s} с` : 'нет решений'} />
          </section>
          <div className="cab-grid cab-grid--2">
            <ErrorsCard title="Характерные недостатки" rows={d.top_errors} empty="Замечаний нет — отличная смена." />
            <Card title="На что обратить внимание" subtitle="Самые слабые критерии группы и совет">
              {d.weak_criteria.length
                ? <ol className="tch-list">{d.weak_criteria.map((c) => <li key={c.key}><b>{c.title}</b> — {pct(c.average)}<small>{c.advice}</small></li>)}</ol>
                : <p className="c-slate">Все критерии группы выше 85 %.</p>}
              {d.weak_groups.length > 0 && (
                <>
                  <div className="cab-filters__label" style={{ margin: '12px 0 6px' }}>Повторить (балл ниже порога):</div>
                  <ul className="tch-list">{d.weak_groups.map((g) => <li key={g.group_id}>{g.group_id}. {g.title} — {num(g.avg_score)}</li>)}</ul>
                </>
              )}
            </Card>
          </div>
          <div className="cab-grid cab-grid--2">
            <Card title="Сверх норматива" flush>
              <table className="cab-table">
                <thead><tr><th>Кто</th><th>Карточка</th><th className="num">Время</th><th className="num">Норматив</th></tr></thead>
                <tbody>
                  {d.overdue.map((o) => (
                    <tr key={`${o.who}${o.card_number}${o.role}`}>
                      <td>{o.who} · {roleLabel(o.role)}</td><td>№ {o.card_number}</td>
                      <td className="num c-red">{num(o.time_s)} с</td><td className="num">{o.norm_s} с</td>
                    </tr>
                  ))}
                  {!d.overdue.length && <tr><td colSpan={4} className="c-slate">Все уложились в норматив.</td></tr>}
                </tbody>
              </table>
            </Card>
            <Card title="Лучшие результаты" subtitle="Отметить на разборе">
              {d.best.length
                ? <ol className="tch-list">{d.best.map((b) => <li key={b.who + b.role}><b>{b.who}</b> · {roleLabel(b.role)} — {num(b.avg_score)}</li>)}</ol>
                : <p className="c-slate">Нет оценённых карточек.</p>}
            </Card>
          </div>
        </>
      )}
    </TeacherShell>
  );
}
