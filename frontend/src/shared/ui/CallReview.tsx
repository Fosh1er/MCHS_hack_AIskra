/** Разбор разговора с ИИ-заявителем для преподавателя (п. 3.6, V4): как менялось напряжение заявителя по репликам
 *  и какие слова оператора его изменили. Данные — снимки состояния у реплик заявителя (`GET /training/cards/{id}/calls`). */
import { LineChart } from '@smena112/ui-kit';
import { useCardCalls, type CallMessage, type CallView, type ToneChange } from '../api/training';

const REASON: Record<ToneChange['reason'], string> = {
  calming: 'успокоил',
  invalidating: 'обесценил',
  pressure: 'давил',
  on_topic: 'вопрос по делу',
};
const MODE: Record<string, string> = { text: 'текстом', voice: 'голосом', hands_free: 'голосом без рук' };

const sign = (n: number) => (n > 0 ? `+${n}` : `−${Math.abs(n)}`); // типографский минус

function effect(c: ToneChange): string {
  const parts = [c.tension && `напряжение ${sign(c.tension)}`, c.trust && `доверие ${sign(c.trust)}`].filter(Boolean);
  const what = c.reason === 'on_topic' ? REASON.on_topic : `${REASON[c.reason]}: «${c.fragment}»`;
  return parts.length ? `${what} — ${parts.join(', ')}` : what;
}

function Conversation({ call }: { call: CallView }) {
  const party = call.messages.filter((m) => m.speaker === 'party' && m.tone);
  if (!party.length) return null;
  const first = party[0].tone!;
  const last = party[party.length - 1].tone!;
  // что сделала реплика оператора — в снимке следующей за ней реплики заявителя
  const after = new Map<CallMessage, ToneChange[]>();
  call.messages.forEach((m, i) => {
    const next = call.messages[i + 1];
    if (m.speaker === 'operator' && next?.tone) after.set(m, next.tone.changes.filter((c) => c.reason !== 'on_topic'));
  });
  return (
    <div className="call-review">
      <div className="call-review__sum">
        Напряжение заявителя <b>{first.tension} → {last.tension}</b> из 10 ({first.emotion_title} → {last.emotion_title}),
        доверие {first.trust} → {last.trust}{call.mode ? ` · разговор ${MODE[call.mode] ?? call.mode}` : ''}
      </div>
      {party.length > 1 && (
        <LineChart points={party.map((m, i) => ({ t: `${i + 1}`, v: m.tone!.tension }))} yMax={10} yStep={2}
          unit="из 10" seriesLabel="Напряжение заявителя по его репликам" threshold={{ value: 8, label: 'паника' }} height={160} />
      )}
      <ol className="call-review__lines">
        {call.messages.filter((m) => m.speaker !== 'system').map((m, i) => (
          <li key={m.id ?? i} className={m.speaker === 'operator' ? 'is-operator' : 'is-party'}>
            <span className="call-review__who">
              {m.speaker === 'operator' ? 'Оператор' : `Заявитель${m.tone ? ` · ${m.tone.emotion_title}, ${m.tone.tension}/10` : ''}`}
            </span>
            {m.text}
            {(after.get(m) ?? []).map((c, j) => (
              <span key={j} className={`call-review__effect is-${c.reason}`}>{effect(c)}</span>
            ))}
          </li>
        ))}
      </ol>
    </div>
  );
}

export function CallReview({ cardId }: { cardId: string }) {
  const calls = useCardCalls(cardId);
  if (calls.isLoading) return <div className="call-review">загрузка разговора…</div>;
  const withTone = (calls.data ?? []).filter((c) => c.party === 'applicant' && c.messages.some((m) => m.tone));
  if (!withTone.length) return <div className="call-review">Разговора с заявителем по этой карточке нет.</div>;
  return <>{withTone.map((c) => <Conversation key={c.id} call={c} />)}</>;
}
