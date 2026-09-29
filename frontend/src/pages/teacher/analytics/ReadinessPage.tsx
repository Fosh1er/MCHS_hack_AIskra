/** Готовность к допуску (specs/4.6; ПС 12.002 C/03): оценка по шкале итогового контроля Программы подготовки ЕДДС
 *  по последним карточкам — балл и соблюдение нормативов ПП РФ № 1931; «доп. практика» — индивидуальное задание,
 *  выбранные — в протокол для печати. */
import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Banner, Button, Card, Segmented, StatusPill } from '@smena112/ui-kit';
import { useReadiness, type Readiness } from '../../../shared/api/assessment';
import { useGroups } from '../../../shared/api/admin';
import { TeacherShell } from '../../../shared/ui/TeacherShell';
import { useScreenTour } from '../../../shared/onboarding/OnboardingProvider';
import { num } from '../../../shared/format';
import { pct, roleLabel } from './parts';

type Last = '5' | '10' | '20';
const LAST: { value: Last; label: string }[] = [{ value: '5', label: '5 карточек' }, { value: '10', label: '10' }, { value: '20', label: '20' }];

export function GradePill({ r }: { r: Readiness }) {
  const status = r.grade === null ? 'neutral' : r.grade >= 4 ? 'ok' : r.grade === 3 ? 'warn' : 'critical';
  return <StatusPill status={status}>{r.grade_label}</StatusPill>;
}

export function ReadinessPage() {
  const navigate = useNavigate();
  const [last, setLast] = useState<Last>('10');
  const [group, setGroup] = useState('');
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const q = useReadiness({ last: Number(last) });
  useScreenTour('teacher-readiness', !!q.data);
  const groups = useGroups().data ?? [];
  const members = useMemo(() => new Set(groups.find((g) => g.id === group)?.members.map((m) => m.user_id) ?? []), [groups, group]);
  const rows = (q.data?.rows ?? []).filter((r) => !group || members.has(r.student_id));
  const toggle = (id: string) => setPicked((p) => { const n = new Set(p); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const ids = [...picked].filter((id) => rows.some((r) => r.student_id === id));
  const protocol = () => navigate(`/teacher/readiness/protocol?last=${last}${(ids.length ? ids : [...new Set(rows.map((r) => r.student_id))]).map((id) => `&student=${id}`).join('')}`);
  return (
    <TeacherShell active="readiness" crumbs="Пульт / Допуск" title="Готовность к допуску"
      subtitle="Оценка по последним карточкам: балл и соблюдение нормативов"
      actions={<span className="cab-filters">
        <Segmented options={LAST} value={last} onChange={setLast} ariaLabel="Сколько последних карточек учитывать" />
        <span data-tour="t-protocol"><Button variant="primary" icon="description" disabled={!rows.length} onClick={protocol}>{ids.length ? `протокол (${ids.length})` : 'протокол'}</Button></span>
      </span>}>
      {q.isError && <Banner status="critical">{q.error.message}</Banner>}
      {q.data && (
        <>
          <Card title="Шкала" subtitle={q.data.source} tour="t-scale">
            <ul className="tch-list">{q.data.scale.map((s) => <li key={s.grade}><b>{s.grade}</b> — {s.rule}</li>)}</ul>
            <p className="tch-source">Учитываются последние {q.data.last} оценённых карточек каждой роли; меньше {q.data.min_cards} — «недостаточно данных». Экспертная правка балла учитывается.</p>
          </Card>
          <Card title="Обучающиеся" subtitle="Отметьте строки, чтобы включить в протокол только их" flush tour="t-readiness-list"
            actions={groups.length > 0 && (
              <select className="cab-select" aria-label="Группа" value={group} onChange={(e) => setGroup(e.target.value)}>
                <option value="">все группы</option>
                {groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
              </select>
            )}>
            <table className="cab-table">
              <thead><tr><th /><th>Обучающийся</th><th>Роль</th><th className="num">Карточек</th><th className="num">Средний балл</th><th>Время</th><th>Оценка</th><th>Заключение</th><th /></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.student_id + r.role}>
                    <td><input type="checkbox" aria-label={`В протокол: ${r.full_name}`} checked={picked.has(r.student_id)} onChange={() => toggle(r.student_id)} /></td>
                    <td><Link to={`/teacher/students/${r.student_id}`}><b>{r.full_name}</b></Link></td>
                    <td>{roleLabel(r.role, r.service_code)}</td>
                    <td className="num">{r.readiness.cards}</td>
                    <td className="num">{num(r.readiness.avg_score)}</td>
                    <td>{r.readiness.timing}{r.readiness.within_share !== null ? ` · ${pct(r.readiness.within_share)}` : ''}</td>
                    <td><GradePill r={r.readiness} /></td>
                    <td className={r.readiness.ready ? '' : 'c-red'}>{r.readiness.status}</td>
                    <td>{!r.readiness.ready && r.readiness.grade !== null && (
                      <Button size="sm" variant="ghost" icon="plus" onClick={() => navigate(`/teacher/sessions?assign=${r.student_id}`)}>доп. практика</Button>
                    )}</td>
                  </tr>
                ))}
                {!rows.length && <tr><td colSpan={9} className="c-slate">Нет обучающихся с карточками в ваших занятиях.</td></tr>}
              </tbody>
            </table>
          </Card>
        </>
      )}
    </TeacherShell>
  );
}
