/** Кабинет обучающегося (п. 5.1): идущее занятие и вход в эмулятор своей роли, запланированные, история с
 *  результатами и отзывами преподавателя (п. 4.7), рекомендации по слабым местам. */
import { Fragment } from 'react';
import { useNavigate } from 'react-router-dom';
import { Banner, Button, Card, Icon, StatTile, StatusPill } from '@smena112/ui-kit';
import { useServices } from '../../shared/api/dictionaries';
import { useMyFeedback, useMyProgress } from '../../shared/api/assessment';
import { MODE_TITLE, SESSION_STATUS, armFor, useMySessions, type MySessionRow } from '../../shared/api/training';
import { CabinetShell } from '../../shared/ui/CabinetShell';
import { useScreenTour, useTourControls } from '../../shared/onboarding/OnboardingProvider';
import { num } from '../../shared/format';

function useRole() {
  const services = useServices();
  const names = new Map((services.data ?? []).map((s) => [s.code, s.short]));
  return (s: MySessionRow) => (s.role === '112' ? 'оператор 112' : `диспетчер ДДС «${names.get(s.dds_service_code ?? '') ?? s.dds_service_code}»`);
}

export function StudentHomePage() {
  const navigate = useNavigate();
  const sessions = useMySessions();
  const progress = useMyProgress();
  const myFeedback = useMyFeedback();
  const role = useRole();
  const tour = useTourControls();
  useScreenTour('student-home', !!sessions.data && !!progress.data);
  const all = sessions.data ?? [];
  const running = all.find((s) => s.status === 'running');
  const planned = all.filter((s) => s.status === 'planned');
  const finished = all.filter((s) => s.status === 'finished');
  const p = progress.data;
  const feedback = new Map((myFeedback.data ?? []).map((f) => [f.session_id, f]));
  return (
    <CabinetShell kind="student" active="home" title="Кабинет обучающегося"
      actions={(
        <>
          <span data-tour="help"><Button icon="help" variant="ghost" onClick={tour.restart}>пройти обучение заново</Button></span>
          <Button icon="table" onClick={() => navigate('/arm/112/journal')}>открыть АРМ-112</Button>
        </>
      )}>
      {running ? (
        <div data-tour="session-banner">
          <Banner actions={<Button variant="primary" icon="play" onClick={() => navigate(armFor(running))}>войти в занятие</Button>}>
            Идёт занятие <b>«{running.title}»</b> · {MODE_TITLE[running.mode]} · ваша роль — <b>{role(running)}</b>
          </Banner>
        </div>
      ) : (
        <Banner>Сейчас занятий нет. Потренироваться можно в АРМ-112: кнопка «учебный вызов» в журнале.</Banner>
      )}
      <section className="cab-kpis" data-tour="kpis">
        <StatTile label="Средний балл" value={num(p?.avg_score)} />
        <StatTile label="Оценённых работ" value={p?.points.length ?? 0} />
        <StatTile label="Занятий пройдено" value={finished.length} />
        <StatTile label="Запланировано" value={planned.length} />
      </section>
      <div className="cab-grid cab-grid--2">
        <div className="tour-wrap" data-tour="assigned"><Card title="Назначенные занятия" flush>
          <table className="cab-table">
            <tbody>
              {[...(running ? [running] : []), ...planned].map((s) => (
                <tr key={s.session_id}>
                  <td><b>{s.title}</b><br /><small className="c-slate">{MODE_TITLE[s.mode]} · {role(s)}</small></td>
                  <td><StatusPill status={s.status === 'running' ? 'ok' : 'info'}>{SESSION_STATUS[s.status]}</StatusPill></td>
                  <td>{s.status === 'running' && <Button size="sm" variant="primary" onClick={() => navigate(armFor(s))}>войти</Button>}</td>
                </tr>
              ))}
              {sessions.data && !running && !planned.length && <tr><td className="c-slate">Назначенных занятий нет.</td></tr>}
            </tbody>
          </table>
        </Card></div>
        <div className="tour-wrap" data-tour="recommendations"><Card title="Над чем поработать">
          {p?.recommendations.length
            ? <ul className="stu-recs">{p.recommendations.map((r) => <li key={r.key}><b>{Math.round(r.average * 100)} %</b> {r.text}</li>)}</ul>
            : 'Рекомендации появятся после первых оценённых карточек.'}
        </Card></div>
      </div>
      <div data-tour="history"><Card title="История занятий" flush>
        <table className="cab-table">
          <thead><tr><th>Занятие</th><th>Роль</th><th>Завершено</th><th /></tr></thead>
          <tbody>
            {finished.map((s) => {
              const f = feedback.get(s.session_id);
              return (
                <Fragment key={s.session_id}>
                  <tr className={f ? 'stu-has-feedback' : undefined}>
                    <td>{s.title}</td><td>{role(s)}</td><td>{s.finished_at ? new Date(s.finished_at).toLocaleString('ru-RU') : '—'}</td>
                    <td><Button size="sm" variant="ghost" icon="bar_chart" onClick={() => navigate(`/student/sessions/${s.session_id}`)}>мои результаты</Button></td>
                  </tr>
                  {f && (
                    <tr className="stu-feedback-row">
                      <td colSpan={4}>
                        <div className="stu-feedback">
                          <div className="stu-feedback__head"><Icon name="chat" size="sm" /> <b>Отзыв преподавателя</b>
                            {f.updated_at && <small>{new Date(f.updated_at).toLocaleDateString('ru-RU')}</small>}</div>
                          <p className="stu-feedback__text">{f.text}</p>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
            {sessions.data && !finished.length && <tr><td colSpan={4} className="c-slate">Пройденных занятий пока нет.</td></tr>}
          </tbody>
        </table>
      </Card></div>
    </CabinetShell>
  );
}
