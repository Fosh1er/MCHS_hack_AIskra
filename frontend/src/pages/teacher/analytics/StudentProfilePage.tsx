/** Профиль обучающегося у преподавателя (specs/4.5; ПС 12.002 C/03–C/04): все занятия преподавателя — динамика,
 *  критерии против группы, типичные ошибки, отработанные группы классификатора, сложность, нормативы;
 *  «индивидуальное задание» — занятие по слабым местам. */
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Banner, Button, Card, LineChart, StatTile, StatusPill } from '@smena112/ui-kit';
import { useStudentProfile } from '../../../shared/api/assessment';
import { TeacherShell } from '../../../shared/ui/TeacherShell';
import { num } from '../../../shared/format';
import { ErrorsCard, NormTiles, pct, when } from './parts';

const delta = (d: number | null) => (d === null ? '—' : `${d > 0 ? '+' : ''}${Math.round(d * 100)}`);

export function StudentProfilePage() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const q = useStudentProfile(id);
  const p = q.data;
  return (
    <TeacherShell active="analytics" crumbs="Пульт / Аналитика / Обучающийся" title={p?.full_name ?? 'Профиль обучающегося'}
      subtitle={p ? `${p.roles.map((r) => (r === '112' ? 'оператор 112' : 'диспетчер ДДС')).join(', ')} · занятий: ${p.sessions}` : undefined}
      actions={<span className="tch-noprint cab-filters">
        <Button variant="primary" icon="plus" onClick={() => navigate(`/teacher/sessions?assign=${id}`)}>индивидуальное задание</Button>
        <Button icon="description" onClick={() => window.print()}>PDF</Button>
      </span>}>
      {q.isError && <Banner status="critical">{q.error.message}</Banner>}
      {p && (
        <>
          <section className="cab-kpis">
            <StatTile label="Средний балл" value={num(p.avg_score)} />
            <StatTile label="Зачтено" value={pct(p.passed_share)} />
            <StatTile label="Карточек" value={p.cards} />
            <StatTile label="Занятий" value={p.sessions} />
          </section>
          {p.points.length >= 2 && (
            <Card title="Динамика баллов" subtitle="Каждая точка — оценённая карточка, по времени">
              <LineChart points={p.points.map((x) => ({ t: when(x.t), v: x.v }))}
                yMax={100} yStep={20} unit="балл" seriesLabel="Балл за карточку" threshold={{ value: 70, label: 'порог' }} />
            </Card>
          )}
          <div className="cab-grid cab-grid--2">
            <Card title="Критерии против группы" subtitle="Средний балл критерия, %; разница — с остальными обучающимися в той же роли" flush>
              <table className="cab-table">
                <thead><tr><th>Критерий</th><th className="num">Обучающийся</th><th className="num">Группа</th><th className="num">Разница</th></tr></thead>
                <tbody>
                  {p.criteria.map((c) => (
                    <tr key={c.key}>
                      <td>{c.title}</td>
                      <td className="num">{Math.round(c.student * 100)}</td>
                      <td className="num">{c.group === null ? '—' : Math.round(c.group * 100)}</td>
                      <td className={`num ${c.delta !== null && c.delta <= -0.1 ? 'c-red' : c.delta !== null && c.delta >= 0.1 ? 'c-green' : ''}`}>{delta(c.delta)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
            <ErrorsCard title="Типичные ошибки" rows={p.frequent_errors} empty="Замечаний нет." />
          </div>
          <div className="cab-grid cab-grid--2">
            <Card title="Группы классификатора" subtitle="Что отрабатывалось — по сценарию вызова" flush>
              <table className="cab-table">
                <thead><tr><th>Группа</th><th className="num">Карточек</th><th className="num">Средний балл</th><th className="num">Замечаний</th></tr></thead>
                <tbody>
                  {p.coverage.map((g) => (
                    <tr key={g.group_id}>
                      <td>{g.group_id}. {g.title}</td>
                      <td className="num">{g.cards}</td>
                      <td className={`num ${g.avg_score !== null && g.avg_score < 70 ? 'c-red' : ''}`}>{num(g.avg_score)}</td>
                      <td className="num">{g.errors}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {p.not_practiced.length > 0 && (
                <div style={{ padding: 12 }}>
                  <div className="cab-filters__label" style={{ marginBottom: 6 }}>Ещё не встречались (в банке есть утверждённые сценарии):</div>
                  <div className="tch-chips">{p.not_practiced.map((g) => <StatusPill key={g.group_id} status="neutral">{g.group_id}. {g.title} · {g.approved}</StatusPill>)}</div>
                </div>
              )}
            </Card>
            <Card title="Рекомендации" subtitle="По самым слабым критериям — для инструктажа">
              {p.recommendations.length
                ? <ul className="tch-list">{p.recommendations.map((r) => <li key={r.key}>{r.text} <small>средний балл критерия {pct(r.average)}</small></li>)}</ul>
                : <p className="c-slate">Все критерии выше 85 %.</p>}
              {p.by_difficulty.length > 0 && (
                <>
                  <div className="cab-filters__label" style={{ margin: '12px 0 6px' }}>Балл по сложности заявителя:</div>
                  <div className="tch-chips">
                    {p.by_difficulty.map((d) => <StatusPill key={d.difficulty} status={d.avg_score !== null && d.avg_score < 70 ? 'critical' : 'ok'}>сложность {d.difficulty}: {num(d.avg_score)} ({d.cards})</StatusPill>)}
                  </div>
                </>
              )}
            </Card>
          </div>
          {p.card_112.count > 0 && <Card title="Карточка 112: время против норматива"><NormTiles label="Карточки" stat={p.card_112} /></Card>}
          {p.dds.count > 0 && <Card title="ДДС: время решения против норматива"><NormTiles label="Решения" stat={p.dds} /></Card>}
          <p className="tch-source tch-noprint"><Link to="/teacher/analytics">← к аналитике</Link></p>
        </>
      )}
    </TeacherShell>
  );
}
