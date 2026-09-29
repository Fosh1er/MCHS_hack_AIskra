/** Мои результаты по занятию (п. 5.1): отзыв преподавателя по занятию (п. 4.7), карточки, балл, время против
 *  норматива, разбор ошибок, комментарии преподавателя и рекомендации. */
import { useParams } from 'react-router-dom';
import { Banner, Card, StatTile, StatusPill } from '@smena112/ui-kit';
import { useMySessionReport } from '../../shared/api/assessment';
import { CabinetShell } from '../../shared/ui/CabinetShell';
import { num } from '../../shared/format';

export function MySessionPage() {
  const { id = '' } = useParams();
  const q = useMySessionReport(id);
  const r = q.data?.report;
  const me = r?.students[0];
  return (
    <CabinetShell kind="student" active="home" crumbs="Кабинет / История" title={r ? r.title : 'Результаты занятия'}
      subtitle={r?.finished_at ? `завершено ${new Date(r.finished_at).toLocaleString('ru-RU')}` : undefined}>
      {q.isError && <Banner status="critical">{q.error.message}</Banner>}
      {me && (
        <>
          <section className="cab-kpis">
            <StatTile label="Средний балл" value={num(me.avg_score)} note={`порог ${r!.settings.threshold ?? 70}`} />
            <StatTile label="Зачтено" value={me.passed_share === null ? '—' : `${Math.round(me.passed_share * 100)} %`} />
            <StatTile label="Карточек" value={me.cards.length} />
            <StatTile label="Среднее время" value={num(me.avg_time_s)} unit={me.avg_time_s ? 'с' : undefined} />
          </section>
          {me.not_assessed > 0 && <Banner>Не оценено карточек: {me.not_assessed}. Оценку запускает преподаватель.</Banner>}
          {me.feedback && (
            <Card title="Отзыв преподавателя" subtitle={me.feedback.updated_at ? new Date(me.feedback.updated_at).toLocaleString('ru-RU') : undefined}>
              <p className="stu-feedback__text">{me.feedback.text}</p>
            </Card>
          )}
          {q.data!.recommendations.length > 0 && (
            <Card title="Рекомендации">
              <ul className="stu-recs">{q.data!.recommendations.map((x) => <li key={x.key}><b>{Math.round(x.average * 100)} %</b> {x.text}</li>)}</ul>
            </Card>
          )}
          <Card title="Разбор карточек">
            {me.cards.map((c) => (
              <div key={c.card_id} className="stu-card">
                <div className="tch-cardline">
                  <b>№ {c.card_number}</b>
                  {c.processing_s !== null && (
                    <span className={c.deviation_s !== null && c.deviation_s > 0 ? 'c-red' : ''}>
                      {Math.round(c.processing_s)} с при нормативе {c.norm_s} с
                    </span>
                  )}
                  {c.score !== null
                    ? <StatusPill status={c.passed ? 'ok' : 'critical'}>{num(c.score)} · {c.passed ? 'зачтено' : 'не зачтено'}</StatusPill>
                    : <StatusPill status="neutral">не оценена</StatusPill>}
                </div>
                {c.expert_comment && <div className="tch-expert">Преподаватель: {c.expert_comment}</div>}
                {c.errors.length > 0 ? <ul className="tch-errors">{c.errors.map((e) => <li key={e}>{e}</li>)}</ul> : c.score !== null && <p className="c-slate">Ошибок нет.</p>}
              </div>
            ))}
            {!me.cards.length && 'Карточек в этом занятии нет.'}
          </Card>
        </>
      )}
    </CabinetShell>
  );
}
