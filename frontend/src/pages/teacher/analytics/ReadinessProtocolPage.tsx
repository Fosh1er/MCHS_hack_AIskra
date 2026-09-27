/** Протокол оценки готовности (specs/4.6; ПС 12.002 C/03 — «проведение аттестации и оформление протокола»):
 *  документ для печати по выбранным обучающимся — основание, параметры, оценки, заключения, подписи. */
import { useSearchParams } from 'react-router-dom';
import { Banner, Button } from '@smena112/ui-kit';
import { useReadiness } from '../../../shared/api/assessment';
import { TeacherShell } from '../../../shared/ui/TeacherShell';
import { num } from '../../../shared/format';
import { pct, roleLabel } from './parts';

export function ReadinessProtocolPage() {
  const [params] = useSearchParams();
  const last = Number(params.get('last') ?? 10) || 10;
  const students = params.getAll('student');
  const q = useReadiness({ last, studentIds: students });
  const v = q.data;
  const date = v ? new Date(v.generated_at) : new Date();
  return (
    <TeacherShell active="readiness" crumbs="Пульт / Допуск / Протокол" title="Протокол оценки готовности"
      actions={<span className="tch-noprint cab-filters"><Button variant="primary" icon="description" onClick={() => window.print()}>печать / PDF</Button></span>}>
      {q.isError && <Banner status="critical">{q.error.message}</Banner>}
      {v && (
        <article className="tch-protocol">
          <h2>ПРОТОКОЛ № ______</h2>
          <p className="tch-protocol__sub">оценки готовности обучающихся к самостоятельной работе<br />(тренажёр «АИскра»)</p>
          <p>Дата: {date.toLocaleDateString('ru-RU')}. Преподаватель: {v.teacher}.</p>
          <p>Основание: {v.source}.</p>
          <p>Порядок оценки: по последним {v.last} оценённым учебным карточкам каждой роли — средний балл автооценки
            (с учётом экспертных правок преподавателя) и доля карточек в нормативе времени (карточка 112 — 75 с, решение ДДС — 30 с).
            Меньше {v.min_cards} карточек — оценка не ставится.</p>
          <table className="tch-protocol__table">
            <thead><tr><th>№</th><th>ФИО</th><th>Роль</th><th>Карточек</th><th>Средний балл</th><th>В нормативе</th><th>Оценка</th><th>Заключение</th></tr></thead>
            <tbody>
              {v.rows.map((r, i) => (
                <tr key={r.student_id + r.role}>
                  <td>{i + 1}</td><td>{r.full_name}</td><td>{roleLabel(r.role, r.service_code)}</td>
                  <td>{r.readiness.cards}</td><td>{num(r.readiness.avg_score)}</td><td>{pct(r.readiness.within_share)}</td>
                  <td>{r.readiness.grade_label}</td>
                  <td>{r.readiness.status}{r.readiness.reasons.length ? <small>{r.readiness.reasons.join('; ')}</small> : null}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!v.rows.length && <p className="c-slate">Нет данных по выбранным обучающимся.</p>}
          <p>Шкала: {v.scale.map((s) => `«${s.grade}» — ${s.rule}`).join('; ')}.</p>
          <div className="tch-protocol__signs">
            <div>Преподаватель ____________________ / {v.teacher} /</div>
            <div>Руководитель ____________________ / ____________________ /</div>
          </div>
        </article>
      )}
    </TeacherShell>
  );
}
