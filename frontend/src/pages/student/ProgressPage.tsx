/** «Мои результаты» (п. 4.3, ТЗ «визуализация прогресса обучающихся»): динамика баллов, слабые места, последние
 *  замечания и экспертные комментарии преподавателя. */
import { Card, LineChart, StatTile } from '@smena112/ui-kit';
import { useMe } from '../../shared/api/auth';
import { useMyProgress } from '../../shared/api/assessment';
import { ArmTopBar } from '../../shared/ui/ArmTopBar';
import { ARM_MENU } from '../../shared/ui/armMenu';

export function ProgressPage() {
  const me = useMe().data!;
  const q = useMyProgress();
  const d = q.data;
  const passed = d ? d.points.filter((p) => p.passed).length : 0;
  return (
    <div className="arm-journal" style={{ minHeight: '100vh' }}>
      <div className="arm-search">
        <div className="arm-search__main"><h1 className="cab-title" style={{ margin: 0 }}>Мои результаты</h1><p style={{ marginTop: 8 }}>{me.full_name}</p></div>
        <ArmTopBar me={me} menu={ARM_MENU} />
      </div>
      <div className="arm-list progress-page">
        {q.isError && <div className="arm-empty">Не удалось загрузить результаты: {q.error.message}</div>}
        {d && !d.points.length && <div className="arm-empty">Оценок пока нет — они появятся после проверки ваших карточек.</div>}
        {d && d.points.length > 0 && (
          <>
            <section className="cab-kpis">
              <StatTile label="Средний балл" value={d.avg_score ?? '—'} />
              <StatTile label="Оценённых работ" value={d.points.length} />
              <StatTile label="Зачтено" value={`${passed} из ${d.points.length}`} />
            </section>
            {d.points.length >= 2 && (
              <Card title="Динамика баллов">
                <LineChart points={d.points.map((p) => ({ t: `№${p.card_number ?? ''}`, v: p.v }))} yMax={100} yStep={20} unit="балл"
                  seriesLabel="Балл за работу" threshold={{ value: 70, label: 'порог' }} />
              </Card>
            )}
            <div className="cab-grid cab-grid--2">
              <Card title="Над чем поработать">
                {!d.weakest.some((w) => w.average < 0.85) && 'Слабых мест нет — так держать.'}
                <ul className="assess__list">
                  {d.weakest.filter((w) => w.average < 0.85).map((w) => (
                    <li key={w.key} className="assess__item">
                      <span className="assess__title">{w.title}</span>
                      <span className="assess__bar" aria-label={`${Math.round(w.average * 100)} %`}>
                        <span style={{ width: `${Math.round(w.average * 100)}%` }} className={w.average >= 0.7 ? 'ok' : w.average >= 0.4 ? 'warn' : 'bad'} />
                      </span>
                    </li>
                  ))}
                </ul>
              </Card>
              {d.expert_comments.length > 0 && (
                <Card title="Комментарии преподавателя">
                  <ul style={{ margin: 0, paddingLeft: 18 }}>
                    {d.expert_comments.map((c, i) => <li key={i}>Карточка № {c.card_number}: <b>{c.score}</b> — {c.comment}</li>)}
                  </ul>
                </Card>
              )}
              <Card title="Последние замечания">
                {d.recent_errors.length ? <ul style={{ margin: 0, paddingLeft: 18 }}>{d.recent_errors.map((e) => <li key={e}>{e}</li>)}</ul> : 'Замечаний нет.'}
              </Card>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
