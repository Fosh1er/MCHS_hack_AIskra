/** Стартовые разделы преподавателя и обучающегося. Наполнение — пункты 4.x (преподаватель) и 1.x, 5.1 (обучающийся). */
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { PERMISSIONS, useMe } from '../shared/api/auth';
import { keyCode } from './card112/useHotkeys';
import { ArmTopBar } from '../shared/ui/ArmTopBar';
import { ARM_MENU } from '../shared/ui/armMenu';
import { useInsights } from '../shared/api/assessment';
import { Button, Card, StatusPill } from '@smena112/ui-kit';
import { MODE_TITLE, SESSION_STATUS, useMySession, useSessions } from '../shared/api/training';
import { SessionBanner } from '../shared/ui/SessionBanner';
import { TeacherShell } from '../shared/ui/TeacherShell';

const NEXT: Record<string, string> = {
  student: 'Кабинет обучающегося: назначенное занятие, эмулятор АРМ-112 и АРМ ДДС, мои результаты.',
};

/** Пульт преподавателя (п. 4.x): идущие и последние занятия, переходы, инсайты по группе. */
function TeacherHome() {
  const navigate = useNavigate();
  const sessions = useSessions();
  const items = sessions.data?.items ?? [];
  const recent = [...items.filter((s) => s.status === 'running'), ...items.filter((s) => s.status !== 'running')].slice(0, 6);
  return (
    <TeacherShell active="home" title="Пульт преподавателя"
      actions={<>
        <Button icon="library" onClick={() => navigate('/teacher/scenarios')}>банк сценариев</Button>
        <Button variant="primary" icon="plus" onClick={() => navigate('/teacher/sessions')}>занятие</Button>
      </>}>
      <Card title="Занятия" subtitle="Идущие — первыми" flush>
        <table className="cab-table">
          <tbody>
            {recent.map((s) => (
              <tr key={s.id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/teacher/sessions/${s.id}`)}>
                <td><b>{s.title}</b></td><td>{MODE_TITLE[s.mode]}</td><td className="num">{s.participants.length} уч.</td>
                <td><StatusPill status={s.status === 'running' ? 'ok' : s.status === 'planned' ? 'info' : 'neutral'}>{SESSION_STATUS[s.status]}</StatusPill></td>
              </tr>
            ))}
            {sessions.data && !recent.length && <tr><td className="c-slate">Занятий пока нет — создайте первое.</td></tr>}
          </tbody>
        </table>
      </Card>
      <Card title="Инсайты по группе"><GroupInsights /></Card>
    </TeacherShell>
  );
}

/** Инсайты по группе (п. 3.4): слабые критерии и частые ошибки по последним автооценкам. */
function GroupInsights() {
  const q = useInsights(true);
  const d = q.data;
  if (q.isError) return <div className="arm-empty">Не удалось загрузить инсайты: {q.error.message}</div>;
  if (!d) return null;
  if (!d.assessments) return <div className="arm-empty">Оценок пока нет — они появятся, когда обучающиеся сохранят карточки.</div>;
  return (
    <div className="insights">
      <div className="arm-panel">
        <div className="arm-panel__label">Оценок</div><div className="insights__kpi">{d.assessments}</div>
        <div className="arm-panel__label">Средний балл</div><div className="insights__kpi">{d.average_score}</div>
        <div className="arm-panel__label">Зачтено</div><div className="insights__kpi">{Math.round(d.passed_share * 100)} %</div>
      </div>
      <div className="arm-panel">
        <b>Слабые места группы</b>
        <ul className="assess__list" style={{ marginTop: 8 }}>
          {d.weakest.map((w) => (
            <li key={w.key} className="assess__item">
              <span className="assess__title">{w.title} <small className="assess__na">({w.checked})</small></span>
              <span className="assess__bar" aria-label={`${Math.round(w.average * 100)} %`}><span style={{ width: `${Math.round(w.average * 100)}%` }} className={w.average >= 0.7 ? 'ok' : w.average >= 0.4 ? 'warn' : 'bad'} /></span>
            </li>
          ))}
        </ul>
      </div>
      <div className="arm-panel">
        <b>Частые ошибки</b>
        <ol style={{ margin: '8px 0 0', paddingLeft: 18, fontSize: 13 }}>
          {d.frequent_errors.map((e) => <li key={e.text}>{e.text} — <b>{e.count}</b></li>)}
        </ol>
      </div>
    </div>
  );
}

export function RoleHomePage() {
  const me = useMe().data!;
  return me.role === 'teacher' ? <TeacherHome /> : <StudentHome />;
}

function StudentHome() {
  const me = useMe().data!;
  const navigate = useNavigate();
  const canCreate = me.permissions.includes(PERMISSIONS.trainingParticipate);
  const session = useMySession(canCreate).data ?? null;
  useEffect(() => {
    if (!canCreate) return;
    const onKey = (e: KeyboardEvent) => { if (keyCode(e) === 'Insert') navigate('/arm/112'); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [canCreate, navigate]);
  return (
    <div className="arm-journal" style={{ minHeight: '100vh' }}>
      <div className="arm-search">
        <div className="arm-search__main">
          <h1 className="cab-title" style={{ margin: 0 }}>{me.role_title}</h1>
          <p style={{ marginTop: 8 }}>{NEXT[me.role] ?? ''}</p>
          {canCreate && (
            <button type="button" className="arm-bigbtn arm-bigbtn--alert" style={{ marginTop: 12 }} onClick={() => navigate('/arm/112')}>
              создать новую карточку (Insert)
            </button>
          )}
        </div>
        <ArmTopBar me={me} menu={ARM_MENU} />
      </div>
      {session && <SessionBanner s={session} here={session.role === 'dds' ? '112' : 'dds'} />}
    </div>
  );
}
