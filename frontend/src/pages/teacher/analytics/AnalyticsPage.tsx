/** Аналитика преподавателя (specs/4.5): «норматив / факт» по ПП РФ № 1931 за период — в целом, по обучающимся
 *  и по занятиям; переход в профиль обучающегося. Видны только занятия самого преподавателя. */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Banner, Card, Segmented } from '@smena112/ui-kit';
import { useNormReport } from '../../../shared/api/assessment';
import { useStudents } from '../../../shared/api/training';
import { TeacherShell } from '../../../shared/ui/TeacherShell';
import { useScreenTour } from '../../../shared/onboarding/OnboardingProvider';
import { NormTiles, Share, sec } from './parts';

type Period = '7' | '30' | '90' | '0';
const PERIODS: { value: Period; label: string }[] = [
  { value: '7', label: '7 дней' }, { value: '30', label: '30 дней' }, { value: '90', label: '90 дней' }, { value: '0', label: 'всё время' },
];

export function AnalyticsPage() {
  const [period, setPeriod] = useState<Period>('30');
  const q = useNormReport(Number(period) || null);
  const students = useStudents();
  useScreenTour('teacher-analytics', !!q.data);
  const r = q.data;
  const seen = new Set(r?.by_student.map((s) => s.key));
  return (
    <TeacherShell active="analytics" crumbs="Пульт / Аналитика" title="Аналитика"
      subtitle="Время против нормативов, профили обучающихся"
      actions={<Segmented options={PERIODS} value={period} onChange={setPeriod} ariaLabel="Период" />}>
      {q.isError && <Banner status="critical">{q.error.message}</Banner>}
      {r && (
        <>
          <p className="tch-source">Период — {r.period}; нормативы — {r.source}. Для оператора — время от открытия карточки до сохранения, для ДДС — от поступления карточки до решения.</p>
          <Card title="Карточка 112: опрос и заполнение" tour="t-norms"><NormTiles label="Карточки 112" stat={r.card_112} /></Card>
          <Card title="ДДС: подтверждение приёма карточки"><NormTiles label="Решения ДДС" stat={r.dds} /></Card>
          <Card title="По обучающимся" subtitle="Нажмите ФИО — профиль по всем занятиям" flush tour="t-by-students">
            <table className="cab-table">
              <thead><tr><th>Обучающийся</th><th className="num">Карточек</th><th>В нормативе</th><th className="num">Медиана</th><th className="num">90-й процентиль</th><th className="num">Норматив</th></tr></thead>
              <tbody>
                {r.by_student.map((s) => (
                  <tr key={s.key + s.role}>
                    <td><Link to={`/teacher/students/${s.key}`}><b>{s.title}</b></Link>{s.role === '112' ? ' · оператор 112' : ''}</td>
                    <td className="num">{s.stat.count}</td>
                    <td><Share value={s.stat.within_share} /></td>
                    <td className="num">{sec(s.stat.median_s)}</td>
                    <td className="num">{sec(s.stat.p90_s)}</td>
                    <td className="num">{sec(s.stat.norm_s)}</td>
                  </tr>
                ))}
                {!r.by_student.length && <tr><td colSpan={6} className="c-slate">За период нет карточек в ваших занятиях.</td></tr>}
              </tbody>
            </table>
          </Card>
          <Card title="По занятиям" flush>
            <table className="cab-table">
              <thead><tr><th>Занятие</th><th>Дата</th><th>112 в нормативе</th><th>ДДС в нормативе</th><th /></tr></thead>
              <tbody>
                {r.by_session.map((s) => (
                  <tr key={s.session_id}>
                    <td><b>{s.title}</b></td>
                    <td>{s.at ? new Date(s.at).toLocaleDateString('ru-RU') : '—'}</td>
                    <td><Share value={s.card_112.within_share} /></td>
                    <td><Share value={s.dds.within_share} /></td>
                    <td><Link to={`/teacher/sessions/${s.session_id}/debrief`}>разбор</Link> · <Link to={`/teacher/sessions/${s.session_id}/report`}>отчёт</Link></td>
                  </tr>
                ))}
                {!r.by_session.length && <tr><td colSpan={5} className="c-slate">Занятий за период нет.</td></tr>}
              </tbody>
            </table>
          </Card>
        </>
      )}
      {students.data && students.data.some((s) => !seen.has(s.id)) && (
        <Card title="Остальные обучающиеся" subtitle="Без карточек за период">
          <div className="tch-chips">
            {students.data.filter((s) => !seen.has(s.id)).map((s) => <Link key={s.id} className="cab-btn" to={`/teacher/students/${s.id}`}>{s.full_name}</Link>)}
          </div>
        </Card>
      )}
    </TeacherShell>
  );
}
