/** Частичное утверждение эталона (п. 3.3): по каждому разделу — «принять» или «на доработку» с комментарием.
 *  Все разделы приняты — сценарий утверждён; раздел, изменённый после решения, снова ждёт проверки. */
import { useEffect, useState } from 'react';
import { Banner, Button, Segmented, StatusPill } from '@smena112/ui-kit';
import { useReviewSections, type SectionDecision, type SectionReview, type ScenarioView } from '../../shared/api/training';

type Draft = Record<string, SectionDecision>;

const fromView = (rows: SectionReview[]): Draft =>
  Object.fromEntries(rows.filter((r) => r.decision).map((r) => [r.key, { decision: r.decision!, comment: r.comment }]));

function Pill({ r }: { r: SectionReview }) {
  if (r.decision === 'accepted') return <StatusPill status="ok">принят</StatusPill>;
  if (r.decision === 'rework') return <StatusPill status="warn">на доработке</StatusPill>;
  if (r.stale) return <StatusPill status="info">изменён после проверки</StatusPill>;
  return <StatusPill status="neutral">не проверен</StatusPill>;
}

export function ReferenceReview({ s }: { s: ScenarioView }) {
  const rows = s.review ?? [];
  const save = useReviewSections();
  const [draft, setDraft] = useState<Draft>(() => fromView(rows));
  const [info, setInfo] = useState('');
  useEffect(() => setInfo(''), [s.id]); // итог сохранения — до перехода к другому сценарию
  useEffect(() => setDraft(fromView(s.review ?? [])), [s.id, s.review]);
  if (!rows.length) return null;

  const set = (key: string, patch: Partial<SectionDecision>) =>
    setDraft({ ...draft, [key]: { ...(draft[key] ?? { decision: 'accepted', comment: '' }), ...patch } });
  const changed = Object.fromEntries(Object.entries(draft).filter(([k, d]) => {
    const was = rows.find((r) => r.key === k);
    return d.decision !== was?.decision || (d.decision === 'rework' && (d.comment ?? '') !== was?.comment);
  }));
  const missing = Object.values(changed).some((d) => d.decision === 'rework' && !(d.comment ?? '').trim());
  const accepted = rows.filter((r) => r.decision === 'accepted').length;
  const submit = () => save.mutate({ id: s.id, sections: changed }, {
    onSuccess: (r) => setInfo(r.status === 'approved'
      ? 'Все разделы приняты — сценарий утверждён и доступен в занятиях.'
      : `Принято разделов: ${r.sections.filter((x) => x.decision === 'accepted').length} из ${r.sections.length}. Сценарий остаётся на проверке.`),
  });

  return (
    <div className="tch-form" style={{ marginTop: 12 }} data-tour="t-review">
      <div className="cab-filters__label">
        Проверка эталона по разделам: принято {accepted} из {rows.length}
        {s.status === 'approved' ? ' · сценарий утверждён' : ''}
      </div>
      <ol className="tch-review">
        {rows.map((r) => {
          const d = draft[r.key];
          return (
            <li key={r.key}>
              <div className="tch-review__head"><span>{r.title}</span><Pill r={r} /></div>
              <Segmented ariaLabel={`Решение: ${r.title}`} value={d?.decision ?? ''}
                onChange={(v) => v && set(r.key, { decision: v as SectionDecision['decision'] })}
                options={[{ value: 'accepted', label: 'принять' }, { value: 'rework', label: 'на доработку' }]} />
              {d?.decision === 'rework' && (
                <textarea rows={2} aria-label={`Что доработать: ${r.title}`} maxLength={500}
                  placeholder="Что доработать" value={d.comment ?? ''} onChange={(e) => set(r.key, { comment: e.target.value })} />
              )}
              {r.decision === 'rework' && d?.decision !== 'rework' && r.comment && <small className="c-slate">было: {r.comment}</small>}
            </li>
          );
        })}
      </ol>
      <div className="cab-filters">
        <Button icon="check" disabled={s.status === 'archived' || save.isPending || !Object.keys(changed).length || missing} onClick={submit}>
          сохранить решение по разделам
        </Button>
        {missing && <small className="c-slate">Для раздела «на доработку» напишите, что исправить.</small>}
      </div>
      {info && <Banner>{info}</Banner>}
      {save.isError && <Banner status="critical">{save.error.message}</Banner>}
      <small className="c-slate">
        Речь заявителя дорабатывается в режиме «правка» (или перегенерацией по комментарию); после правки её решение сбрасывается,
        принятые разделы остаются принятыми.
      </small>
    </div>
  );
}

/** Замечания «на доработку» — над формой правки, чтобы было видно, что исправить. */
export function ReworkNotes({ s }: { s: ScenarioView }) {
  const notes = (s.review ?? []).filter((r) => r.decision === 'rework');
  if (!notes.length) return null;
  return (
    <Banner status="warn">
      На доработке:
      <ul className="tch-errors">{notes.map((r) => <li key={r.key}><b>{r.title}</b>: {r.comment}</li>)}</ul>
    </Banner>
  );
}
