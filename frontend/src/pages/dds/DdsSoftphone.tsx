/** Симулятор IP-телефона ДДС (п. 2.3), по мотивам РТУ Т16Р (datasheet заказчика): экран линии, DSS-клавиши абонентов,
 *  журнал звонков по карточке. Абоненты — старший группы своей службы, заявитель (номер из карточки, #739),
 *  смежные службы карточки (#701). Отвечают ИИ-собеседники (3.3). Старший группы сам звонит с докладом после
 *  смены статуса (#691). Реальный SIP — вне MVP (#576).
 *  Телефонная книга ДДС (рекомендация экспертов): если преподаватель задал абонентов службы — клавиши из книги и
 *  номеронабиратель; номер не из книги — «Номер не обслуживается», заявителю — только если он есть в книге.
 *  Свёрнутый телефон (рекомендация экспертов) — зелёный кружок с трубкой в правом нижнем углу над панелью служб;
 *  при входящем докладе старшего группы кружок пульсирует. */
import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { Icon, IncomingCall } from '@smena112/ui-kit';
import { useServices } from '../../shared/api/dictionaries';
import type { CardView } from '../../shared/api/incidents';
import { endCall, getCall, startDdsCall, useCardCalls, usePhonebook, useSpeechStatus, type CallView } from '../../shared/api/training';
import { CallPanel } from '../../shared/ui/CallPanel';

const REPORT_AFTER_MS = 12_000; // через сколько старший группы перезванивает с докладом после смены статуса
const REPORT_ON = new Set(['accepted', 'response_started', 'arrived', 'works_in_progress']);
const PARTY_TITLE: Record<CallView['party'], string> = { brigade: 'Старший группы', applicant: 'Заявитель', service: 'Служба' };
const hhmm = (iso: string) => new Date(iso).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });

interface Active { id: string; title: string; party: string }

/** Высота нижней панели служб карточки: телефон висит над ней и не перекрывает. Токен `--arm-svcbar-h` карточка
 *  переопределяет внутри `.arm112`, а телефон рендерится вне её; на узком экране панель переносится в несколько строк. */
function useSvcbarOffset(): CSSProperties | undefined {
  const [h, setH] = useState<number | null>(null);
  useEffect(() => {
    const bar = document.querySelector<HTMLElement>('.arm-svcbar');
    if (!bar) return;
    const ro = new ResizeObserver(() => setH(bar.offsetHeight));
    ro.observe(bar);
    return () => ro.disconnect();
  }, []);
  return h === null ? undefined : ({ '--arm-svcbar-h': `${h}px` } as CSSProperties);
}

export function DdsSoftphone({ card, service, status }: { card: CardView; service: string; status: string }) {
  const catalog = useServices();
  const calls = useCardCalls(card.id);
  const tts = useSpeechStatus().data?.tts ?? false; // запись звонка (п. 8.7) собирается серверным синтезом
  const book = usePhonebook(service).data;
  const contacts = book?.configured ? book.entries : null; // null — книги нет, телефон работает как раньше
  const [active, setActive] = useState<Active | null>(null);
  const [ring, setRing] = useState<string | null>(null); // статус, по которому звонит старший группы
  // по умолчанию свёрнут в кружок на любой ширине: развёрнутая панель закрыла бы карточку (6.3, рекомендация экспертов)
  const [collapsed, setCollapsed] = useState(true);
  const [error, setError] = useState('');
  const [dialed, setDialed] = useState('');
  const reported = useRef(new Set<string>());
  const above = useSvcbarOffset();

  const own = card.services.find((s) => s.code === service);
  const orderNo = [...(own?.history ?? [])].reverse().find((h) => h.order_no)?.order_no;
  const phone = card.data.phones?.provided || card.data.phones?.aon || '';
  const others = card.services.filter((s) => s.code !== service);
  const phoneOf = (code: string) => catalog.data?.find((s) => s.code === code)?.phone ?? '';
  const hasApplicant = !contacts || contacts.some((e) => e.role === 'applicant');

  // доклад старшего группы: один раз на каждый статус, если линия свободна
  useEffect(() => {
    if (!REPORT_ON.has(status) || reported.current.has(status)) return;
    const t = setTimeout(() => {
      reported.current.add(status);
      setRing((r) => r ?? status);
    }, REPORT_AFTER_MS);
    return () => clearTimeout(t);
  }, [status]);

  const dial = async (party: CallView['party'], title: string, target?: string, incoming = false, number?: string) => {
    if (active) return;
    setError('');
    try {
      const c = await startDdsCall({ card_id: card.id, service_code: service, party, target_service: target ?? null, incoming, number });
      // набранный номер: кто ответил — абонент книги или заявитель из карточки — знает сервер
      const who = number ? await getCall(c.call_id).catch(() => null) : null;
      const name = who?.contact?.title ?? (who?.party === 'applicant' ? PARTY_TITLE.applicant : null);
      setActive({ id: c.call_id, title: name ? `${name} · ${number}` : title, party: name ?? (party === 'service' ? title : PARTY_TITLE[party]) });
      if (number) setDialed('');
      setCollapsed(false);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const answerReport = () => { setRing(null); void dial('brigade', `Старший группы${orderNo ? ` · наряд ${orderNo}` : ''}`, undefined, true); };
  const rejectReport = () => setRing(null);
  const hangUp = () => { setActive(null); void calls.refetch(); };
  const callNumber = () => { const n = dialed.trim(); if (n) void dial('brigade', n, undefined, false, n); };

  return (
    <>
      {ring && !active && (
        <div className="call-ring">
          <IncomingCall who={`Старший группы${orderNo ? `, наряд ${orderNo}` : ''}`} sub="Входящий доклад о ходе работ" onAnswer={answerReport} onReject={rejectReport} />
        </div>
      )}
      {active ? (
        <CallPanel callId={active.id} title={active.title} partyName={active.party} onEnded={hangUp} onClose={() => setActive(null)} />
      ) : collapsed ? (
        <button type="button" className={`ipphone-fab${ring ? ' ipphone-fab--ring' : ''}`} style={above} aria-label="IP-телефон"
          title="IP-телефон: набор номера и абоненты" onClick={() => setCollapsed(false)}>
          <Icon name="phone" size="xl" />
        </button>
      ) : (
        <aside className="call-panel arm-dock ipphone" style={above} aria-label="IP-телефон">
          <div className="arm-dock__section ipphone__screen">
            <div className="arm-dock__title">
              <span><Icon name="phone" size="sm" /> IP-телефон · линия свободна</span>
              <button type="button" className="ipphone__toggle" aria-label="Свернуть телефон" title="Свернуть телефон" onClick={() => setCollapsed(true)}>
                <Icon name="expand_more" size="sm" />
              </button>
            </div>
          </div>
          <>
              <div className="arm-dock__section ipphone__keys">
                {contacts ? contacts.filter((e) => e.role !== 'applicant').map((e) => (
                  <button key={e.number} type="button" className="ipphone__key" onClick={() => { void dial('brigade', `${e.title} · ${e.number}`, undefined, false, e.number); }}>
                    <span className="ipphone__led ipphone__led--on" /><b>{e.title}</b><small>{e.name} · {e.number}</small>
                  </button>
                )) : (
                  <button type="button" className="ipphone__key" onClick={() => { void dial('brigade', `Старший группы${orderNo ? ` · наряд ${orderNo}` : ''}`); }}>
                    <span className="ipphone__led ipphone__led--on" /><b>Старший группы</b><small>{orderNo ? `наряд ${orderNo}` : 'наряд не назначен'}</small>
                  </button>
                )}
                {hasApplicant && (
                  <button type="button" className="ipphone__key" disabled={!phone} onClick={() => { void dial('applicant', `Заявитель · ${phone}`); }}>
                    <span className="ipphone__led" /><b>Заявитель</b><small>{phone || 'номера нет'}</small>
                  </button>
                )}
                {others.map((s) => (
                  <button key={s.code} type="button" className="ipphone__key" onClick={() => { void dial('service', s.short, s.code); }}>
                    <span className="ipphone__led" /><b>{s.short}</b><small>{phoneOf(s.code)}</small>
                  </button>
                ))}
              </div>
              {contacts && (
                <form className="arm-dock__section ipphone__dial" onSubmit={(ev) => { ev.preventDefault(); callNumber(); }}>
                  <input aria-label="Номер абонента" placeholder="номер абонента" inputMode="tel" maxLength={24} value={dialed} onChange={(ev) => setDialed(ev.target.value)} />
                  <button type="submit" disabled={!dialed.trim()}>вызов</button>
                </form>
              )}
              {error && <div className="arm-dock__section call-panel__err" role="alert">{error}</div>}
              <div className="arm-dock__section ipphone__log">
                <div className="arm-dock__title"><span>Журнал звонков</span></div>
                {(calls.data ?? []).length === 0 && <div className="call-panel__sub">Звонков по карточке нет</div>}
                {(calls.data ?? []).slice(-6).reverse().map((c) => (
                  <div key={c.id} className="ipphone__logrow">
                    <Icon name={c.direction === 'in' ? 'arrow_down' : 'arrow_up'} size="xs" />
                    {hhmm(c.started_at)} · {c.party === 'service' ? (others.find((s) => s.code === c.target_service)?.short ?? 'служба') : (c.contact?.title ?? PARTY_TITLE[c.party])}
                    {c.ended_at && c.answered_at ? ` · ${Math.round((new Date(c.ended_at).getTime() - new Date(c.answered_at).getTime()) / 1000)} с` : ''}
                    {c.status !== 'ended' && <button type="button" className="ipphone__hang" onClick={() => { void endCall(c.id).then(() => calls.refetch()); }}>сбросить</button>}
                    {c.status === 'ended' && tts && <a className="ipphone__hang" href={`/api/v1/training/calls/${c.id}/recording`} download title="Запись звонка (WAV): реплики обеих сторон синтезом">запись</a>}
                  </div>
                ))}
              </div>
          </>
        </aside>
      )}
    </>
  );
}
