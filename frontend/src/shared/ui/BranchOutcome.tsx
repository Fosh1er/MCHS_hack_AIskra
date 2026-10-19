/** «Итог ситуации» ветвящегося сценария (F5, RF5-05): итог, путь по узлам на временной шкале и на каждой развилке —
 *  что сделал оператор и что было бы при другом решении, со ссылкой на источник. Данные считает сервер
 *  (`training/domain/branching.py:debrief`) — здесь только показ. */
import type { BranchChoice, BranchDebrief, OutcomeCode } from '../api/training';
import { OUTCOME_TITLE } from '../api/training';

const mmss = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
const OUTCOME_CLASS: Record<OutcomeCode, string> = { favorable: 'ok', partial: 'warn', adverse: 'bad', tragic: 'bad' };

function Source({ code, branch }: { code: string; branch: BranchDebrief }) {
  const s = branch.sources[code];
  if (!s) return null;
  return <a className="branch__src" href={s.url} target="_blank" rel="noreferrer" title={s.title}>источник</a>;
}

function Choice({ c, branch, taken }: { c: BranchChoice; branch: BranchDebrief; taken: boolean }) {
  return (
    <li className={taken ? 'is-taken' : ''}>
      <span className="branch__who">{taken ? 'Вы' : 'Иначе'}</span>
      <span>
        {c.label} → {c.effect}
        {c.outcome && <b className={`branch__badge is-${OUTCOME_CLASS[c.outcome]}`}> итог: {OUTCOME_TITLE[c.outcome]}</b>}
        {c.didactic && <em className="branch__note" title="Время развития ситуации — учебное упрощение"> · время учебное</em>}
        {' '}<Source code={c.source} branch={branch} />
      </span>
    </li>
  );
}

export function BranchOutcome({ branch }: { branch: BranchDebrief }) {
  const o = branch.outcome;
  return (
    <div className="branch" aria-label="Итог ситуации">
      <div className="branch__head">
        <b>Развитие ситуации · {branch.title}</b>
        {o
          ? <span className={`branch__badge is-${OUTCOME_CLASS[o.code]}`}>итог: {OUTCOME_TITLE[o.code]}</span>
          : <span className="branch__badge">ситуация развивается: {branch.node_title}</span>}
        {branch.weight ? <span className="assess__meta">вес в балле {Math.round(branch.weight * 100)} %</span> : null}
      </div>
      {o && <p className={`branch__outcome is-${OUTCOME_CLASS[o.code]}`}>{o.text}</p>}
      {!branch.final && <p className="assess__note">Итог будет окончательным, когда разговор завершён и карточка сохранена.</p>}
      <ol className="branch__path" aria-label="Путь по ситуации">
        {branch.path.map((p, i) => <li key={`${p.node}${i}`}><span>{mmss(p.at_s)}</span> {p.title}</li>)}
      </ol>
      {branch.forks.map((f) => (
        <div key={f.node} className="branch__fork">
          <div className="branch__fork-title">{mmss(f.decided_s ?? f.at_s)} · развилка «{f.title}»</div>
          <ul>
            {f.taken && <Choice c={f.taken} branch={branch} taken />}
            {f.others.map((c) => <Choice key={c.to + c.label} c={c} branch={branch} taken={false} />)}
          </ul>
        </div>
      ))}
      <div className="branch__instr" aria-label="Инструкции заявителю">
        {branch.instructions.map((i) => (
          <span key={i.id} className={`psy-act${i.harmful ? ' psy-act--bad' : ''}${i.said_s == null ? ' is-off' : ''}`}
            title={i.harmful ? 'Вредный совет' : 'Инструкция из официальной памятки'}>
            {i.said_s != null ? (i.harmful ? '✗' : '✓') : '—'} {i.title}{i.said_s != null ? ` · ${mmss(i.said_s)}` : ''}
          </span>
        ))}
      </div>
    </div>
  );
}
