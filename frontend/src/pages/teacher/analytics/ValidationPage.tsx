/** Достоверность автооценки (п. 3.5, specs/3.5-validation.md): бенчмарк известных ошибок на утверждённых сценариях,
 *  согласованность генератора и согласие автооценки с экспертными правками преподавателей. */
import { Banner, Card, StatTile, StatusPill } from '@smena112/ui-kit';
import { useValidation } from '../../../shared/api/assessment';
import { TeacherShell } from '../../../shared/ui/TeacherShell';
import { num } from '../../../shared/format';
import { pct } from './parts';

export function ValidationPage() {
  const q = useValidation();
  const v = q.data;
  const b = v?.benchmark;
  return (
    <TeacherShell active="validation" crumbs="Пульт / Достоверность" title="Достоверность автооценки"
      subtitle="Ловит ли автооценка ошибки, не ругается ли зря и совпадает ли с экспертом">
      {q.isError && <Banner status="critical">{q.error.message}</Banner>}
      {q.isLoading && <p className="c-slate">Прогоняю бенчмарк по банку сценариев…</p>}
      {v && b && (
        <>
          <section className="cab-kpis">
            <StatTile label="Ошибка найдена" value={pct(b.detection)} note={`${b.cases} проверок на ${b.scenarios} сценариях`} />
            <StatTile label="Верная работа без замечаний" value={pct(b.specificity_112)} note={`ДДС — ${pct(b.specificity_dds)}`} />
            <StatTile label="Критические → «не зачтено»" value={pct(b.critical_caught)} note={`вердикт верен в ${pct(b.verdict_accuracy)}, κ = ${b.verdict_kappa ?? '—'}`} />
            <StatTile label="Согласие с экспертом" value={v.expert.pairs ? `MAE ${num(v.expert.mae)}` : 'нет правок'}
              note={v.expert.pairs ? `правок ${v.expert.pairs} · вердикт ${pct(v.expert.verdict_agreement)} · κ ${v.expert.kappa ?? '—'}` : 'появится после экспертных правок'} />
          </section>
          <Card title="Бенчмарк известных ошибок" subtitle="В карточку, заполненную по эталону, вносится одна ошибка; критическая должна давать «не зачтено»" flush>
            <table className="cab-table">
              <thead><tr><th>Ошибка</th><th>Роль</th><th>Критерий</th><th /><th className="num">Случаев</th><th>Найдена</th><th>Только этот критерий</th><th>Вердикт верен</th><th className="num">Средний балл</th></tr></thead>
              <tbody>
                {b.mutations.map((m) => (
                  <tr key={m.role + m.key}>
                    <td>{m.title}</td><td>{m.role === '112' ? '112' : 'ДДС'}</td><td>{m.target}</td>
                    <td>{m.critical && <StatusPill status="critical">критическая</StatusPill>}</td>
                    <td className="num">{m.cases}</td><td>{pct(m.detection)}</td><td>{pct(m.localization)}</td><td>{pct(m.verdict_agreement)}</td>
                    <td className="num">{num(m.avg_score)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          <div className="cab-grid cab-grid--2">
            <Card title="Согласованность генератора сценариев" subtitle="То, что скажет заявитель, и то, что считается правильным ответом" flush>
              <table className="cab-table">
                <tbody>{v.generator.map((g) => <tr key={g.key}><td>{g.title}</td><td className="num">{g.checked}</td><td className="num">{pct(g.share)}</td></tr>)}</tbody>
              </table>
            </Card>
            <Card title="Как читать">
              <ul className="tch-list">{v.notes.map((n) => <li key={n}>{n}</li>)}</ul>
            </Card>
          </div>
        </>
      )}
    </TeacherShell>
  );
}
