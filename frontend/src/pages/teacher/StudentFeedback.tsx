/** Отзыв обучающемуся по занятию (specs/4.7). ИИ предлагает черновик по фактам занятия: итог, что получилось, что
 *  подтянуть, следующий шаг. Преподаватель правит и сохраняет — обучающийся увидит отзыв в истории занятий.
 *  Черновик сам ничего не публикует. */
import { useState } from 'react';
import { Banner, Button, StatusPill } from '@smena112/ui-kit';
import { useFeedbackDraft, useSaveFeedback, type FeedbackDraft, type StudentReport } from '../../shared/api/assessment';

const MIN = 10, MAX = 3000;
const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' }) : '');

export function StudentFeedback({ sessionId, student }: { sessionId: string; student: StudentReport }) {
  const saved = student.feedback ?? null;
  const [text, setText] = useState<string | null>(null); // null — отзыв не редактируется
  const [draft, setDraft] = useState<FeedbackDraft | null>(null);
  const suggest = useFeedbackDraft(sessionId, student.student_id);
  const save = useSaveFeedback(sessionId, student.student_id);

  const ask = () => {
    const own = text !== null && text.trim() && text !== draft?.text && text !== saved?.text;
    if (own && !window.confirm('Заменить ваш текст новым черновиком?')) return;
    suggest.mutate(undefined, { onSuccess: (d) => { setDraft(d); setText(d.text); } });
  };
  const close = () => { setText(null); setDraft(null); suggest.reset(); save.reset(); };
  const submit = () => save.mutate(
    { text: text ?? '', ...(draft ? { draft_text: draft.text, draft_source: draft.source, draft_model: draft.model } : {}) },
    { onSuccess: close },
  );

  return (
    <div className={saved ? 'tch-feedback' : 'tch-feedback tch-noprint'}>
      <div className="tch-feedback__head">
        <b>Отзыв по занятию</b>
        {text === null && (
          <small>{saved ? `сохранён ${when(saved.updated_at)} · виден обучающемуся` : 'обучающийся увидит его в истории занятий'}</small>
        )}
      </div>
      {text === null && saved && <p className="tch-feedback__text">{saved.text}</p>}
      {text === null && (
        <div className="cab-filters tch-noprint">
          <Button size="sm" variant={saved ? 'ghost' : 'primary'} icon="bolt" disabled={suggest.isPending} onClick={ask}>
            {suggest.isPending ? 'ИИ пишет черновик…' : saved ? 'предложить заново' : 'предложить отзыв'}
          </Button>
          <Button size="sm" variant="ghost" icon="edit" onClick={() => setText(saved?.text ?? '')}>{saved ? 'изменить' : 'написать самому'}</Button>
        </div>
      )}
      {suggest.isError && <Banner status="critical">{suggest.error.message}</Banner>}
      {text !== null && (
        <div className="tch-form tch-noprint">
          {draft && (
            <div className="tch-feedback__meta">
              <StatusPill status="info">{draft.source === 'ai' ? `черновик ИИ${draft.model ? ` · ${draft.model}` : ''}` : 'черновик по правилам'}</StatusPill>
              <span>Проверьте факты и поправьте текст: обучающийся увидит его только после «сохранить».</span>
            </div>
          )}
          {draft?.warnings.map((w) => <Banner key={w}>{w}</Banner>)}
          {draft?.previous && (
            <details className="tch-feedback__prev">
              <summary>Ваш прошлый отзыв — «{draft.previous.session_title}»{draft.previous.updated_at ? `, ${when(draft.previous.updated_at)}` : ''}</summary>
              <p className="tch-feedback__text">{draft.previous.text}</p>
            </details>
          )}
          <label>
            Текст отзыва
            <textarea rows={Math.min(22, Math.max(8, text.split('\n').length + 4))} value={text} maxLength={MAX} onChange={(e) => setText(e.target.value)} />
          </label>
          <div className="cab-filters">
            <Button size="sm" variant="primary" icon="save" disabled={save.isPending || text.trim().length < MIN} onClick={submit}>
              сохранить отзыв
            </Button>
            <Button size="sm" variant="ghost" icon="bolt" disabled={suggest.isPending} onClick={ask}>
              {suggest.isPending ? 'ИИ пишет…' : draft ? 'другой черновик' : 'предложить черновик'}
            </Button>
            <Button size="sm" variant="ghost" onClick={close}>отмена</Button>
            <span className="cab-filters__label">{text.trim().length} / {MAX}</span>
          </div>
          {save.isError && <Banner status="critical">{save.error.message}</Banner>}
        </div>
      )}
    </div>
  );
}
