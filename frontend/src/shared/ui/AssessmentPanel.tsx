/** Результат автооценки (п. 3.4): итог, «зачтено / не зачтено», критерии с баллом и пояснениями ошибок. */
import { useEffect, useRef, useState } from 'react';
import { Icon } from '@smena112/ui-kit';
import { useAssessment, useEvaluate } from '../api/assessment';
import { num } from '../format';

export function AssessmentPanel({ cardId, role, service, auto }: { cardId: string; role: '112' | 'dds'; service?: string | null; auto: boolean }) {
  const a = useAssessment(cardId, role, service);
  const evaluate = useEvaluate(cardId, role, service);
  const [open, setOpen] = useState(true);
  const started = useRef(false);
  useEffect(() => {
    if (!auto || started.current || a.isPending || a.data) return;
    started.current = true;
    evaluate.mutate();
  }, [auto, a.isPending, a.data, evaluate]);

  const data = a.data;
  return (
    <section className="arm-panel assess" aria-label="Автооценка">
      <div className="assess__head">
        <button type="button" className="assess__toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
          <Icon name={open ? 'expand_less' : 'expand_more'} size="sm" /> <b>Автооценка{role === 'dds' ? ' работы ДДС' : ''}</b>
        </button>
        {data && <span className={`assess__score ${data.passed ? 'assess__score--ok' : 'assess__score--bad'}`}>{num(data.score)} / 100 · {data.passed ? 'зачтено' : 'не зачтено'}</span>}
        <button type="button" className="arm-minibtn" disabled={evaluate.isPending} onClick={() => evaluate.mutate()}>
          {evaluate.isPending ? 'проверяю…' : data ? 'проверить снова' : 'проверить'}
        </button>
      </div>
      {evaluate.isError && <div className="assess__err" role="alert">{evaluate.error.message}</div>}
      {open && data && (
        <>
          {data.details.expert && (
            <p className="assess__expert">
              <b>Оценка преподавателя: {num(data.details.expert.score)}</b> (автооценка {num(data.details.expert.auto_score)}). {data.details.expert.comment}
            </p>
          )}
          {!data.details.has_reference && <p className="assess__note">Карточка заведена без сценария — сравнить с эталоном нельзя, проверено только время.</p>}
          <ul className="assess__list">
            {data.details.criteria.map((c) => (
              <li key={c.key} className="assess__item">
                <span className="assess__title">{c.title}</span>
                {c.score == null
                  ? <span className="assess__na" title={c.note}>не проверено</span>
                  : <span className="assess__bar" aria-label={`${Math.round(c.score * 100)} %`}><span style={{ width: `${Math.round(c.score * 100)}%` }} className={c.score >= 0.7 ? 'ok' : c.score >= 0.4 ? 'warn' : 'bad'} /></span>}
                {c.errors.length > 0 && <ul className="assess__errors">{c.errors.map((e) => <li key={e}>{e}</li>)}</ul>}
              </li>
            ))}
          </ul>
          <p className="assess__meta">Проверка: {data.grader === 'expert' ? 'преподаватель' : data.grader === 'rules+llm' ? 'правила и ИИ-судья' : 'правила'} · версия {data.details.version ?? 1}</p>
        </>
      )}
    </section>
  );
}
