/** Граф ветвящегося сценария для преподавателя (F5, RF5-08): узлы ситуации, переходы по решениям оператора и
 *  итоги — только чтение. Порядок — от старта в ширину, как ситуация может развиваться. */
import { StatusPill } from '@smena112/ui-kit';
import { OUTCOME_TITLE, type BranchGraph, type OutcomeCode } from '../../shared/api/training';

const PILL: Record<OutcomeCode, 'ok' | 'warn' | 'critical'> = { favorable: 'ok', partial: 'warn', adverse: 'critical', tragic: 'critical' };
const TOPIC: Record<string, string> = { address: 'адрес', victims: 'пострадавших', what: 'что случилось', danger: 'угрозу', floor: 'этаж' };

function condition(when: Record<string, string | number | boolean>, g: BranchGraph): string {
  const parts: string[] = [];
  if (when.said) parts.push(`сказал: «${g.instructions[String(when.said)]?.title ?? when.said}»`);
  if (when.asked) parts.push(`заявитель назвал ${TOPIC[String(when.asked)] ?? when.asked}`);
  if (when.act) parts.push(`действие ${when.act}`);
  if (when.card_by_s != null) parts.push(`карточка сохранена до ${when.card_by_s} с`);
  if (when.service) parts.push(`в карточке служба ${when.service}`);
  if (when.dds) parts.push(`ДДС: статус ${when.dds}`);
  if (when.ended) parts.push('разговор завершён');
  if (when.after_s != null) parts.push(`прошло ${when.after_s} с от ответа`);
  return parts.join(' и ');
}

function order(g: BranchGraph): string[] {
  const seen = [g.start];
  for (let i = 0; i < seen.length; i++) {
    for (const e of g.nodes[seen[i]]?.edges ?? []) if (!seen.includes(e.to)) seen.push(e.to);
  }
  return [...seen, ...Object.keys(g.nodes).filter((n) => !seen.includes(n))];
}

export function BranchGraphView({ g }: { g: BranchGraph }) {
  return (
    <div className="branch-graph">
      <p className="c-slate">{g.description} Ситуация оценивается до {Math.round(g.horizon_s / 60)} мин от ответа на вызов.</p>
      <ol className="branch-graph__nodes">
        {order(g).map((id) => {
          const n = g.nodes[id];
          return (
            <li key={id} id={`branch-${id}`} className={n.outcome ? 'is-outcome' : ''}>
              <div className="branch-graph__title">
                <b>{n.title}</b>
                {id === g.start && <StatusPill status="info">старт</StatusPill>}
                {n.outcome && <StatusPill status={PILL[n.outcome.code]}>итог: {OUTCOME_TITLE[n.outcome.code]}</StatusPill>}
              </div>
              {n.situation && <div className="c-slate">{n.situation}</div>}
              {n.event && <div className="branch-graph__event">Заявитель: «{n.event}»</div>}
              {n.outcome && <div>{n.outcome.text}</div>}
              {!!n.edges?.length && (
                <ul className="branch-graph__edges">
                  {n.edges.map((e, i) => (
                    <li key={i}>
                      <span className="c-slate">если {condition(e.when, g)}</span> → <a href={`#branch-${e.to}`}>{g.nodes[e.to]?.title ?? e.to}</a>
                      <br /><small>{e.effect}{e.note === 'didactic' ? ' · время учебное' : ''} · <a href={g.sources[e.source]?.url} target="_blank" rel="noreferrer" title={g.sources[e.source]?.title}>источник</a></small>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ol>
      <details className="tch-details">
        <summary>инструкции заявителю и источники ({Object.keys(g.sources).length})</summary>
        <ul className="tch-errors">
          {Object.entries(g.instructions).map(([id, i]) => <li key={id}>{i.harmful ? '✗ вредный совет: ' : '✓ '}{i.title} — по словам: {i.stems.join(', ')}</li>)}
        </ul>
        <ul className="tch-errors">
          {Object.entries(g.sources).map(([code, s]) => <li key={code}><a href={s.url} target="_blank" rel="noreferrer">{s.title}</a></li>)}
        </ul>
      </details>
    </div>
  );
}
