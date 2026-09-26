/** Просмотр сохранённой карточки 112 (п. 1.3): раскладка стенда 2026 (data/source/screenshots/dds/image6.png),
 *  отработки — по инструкции (instr/image87, image70), история статусов служб — instr/image84, dds/image10.
 *  «просмотр / дополнение» (Shift+F1 / Shift+F2), ЧС / ЧП, «отработана» (Alt+S), «Проверена» (Alt+Y), «Вернуть на доработку» (Alt+N). */
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { CallControl, Icon, IncidentActions, ServiceBar, ServiceTab, SquareButton, StatusHistory } from '@smena112/ui-kit';
import { PERMISSIONS, type Me } from '../../shared/api/auth';
import { useCardTypes, useEnum, useServices } from '../../shared/api/dictionaries';
import {
  CARD_STATUS, SERVICE_STATUS, markCardViewed, useCardActions,
  type CardServiceView, type CardView, type ServiceStatusBody, type WorkoutBody,
} from '../../shared/api/incidents';
import { shortName } from '../../shared/ui/ArmTopBar';
import { AddressMap } from './AddressMap';
import { AssessmentPanel } from '../../shared/ui/AssessmentPanel';
import { Hint } from './Hint';
import { focusId, useHotkeys, type HotkeyMap } from './useHotkeys';

const CARDS_CHECK = 'cards.check';
const pad = (n: number) => String(n).padStart(2, '0');
const dt = (iso: string | null) => (iso ? new Date(iso) : null);
const fmtFull = (d: Date) => `${d.toLocaleDateString('ru-RU')} в ${d.toLocaleTimeString('ru-RU')}`;
const fmtShort = (d: Date) => `${d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit' })}`;
const hhmm = (d: Date) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;
const hhmmss = (d: Date) => `${hhmm(d)}:${pad(d.getSeconds())}`;

/** Поля, которые можно дополнить после сохранения, если они пустые (сервер: domain/incident.py:APPENDABLE_FIELDS). */
const APPENDABLE: { key: string; label: string }[] = [
  { key: 'applicant.name', label: 'ФИО заявителя' },
  { key: 'phones.provided', label: 'предоставленный номер' },
  { key: 'phones.on_site', label: 'телефон на место' },
  { key: 'address.object', label: 'объект' },
  { key: 'address.flat', label: 'квартира/офис' },
  { key: 'address.entrance', label: 'подъезд' },
  { key: 'address.floor', label: 'этаж' },
  { key: 'address.code', label: 'код' },
  { key: 'address.descriptive', label: 'описательный адрес' },
];

function valueAt(data: CardView['data'], key: string): string {
  const [group, name] = key.split('.');
  const g = (data as Record<string, Record<string, unknown> | undefined>)[group];
  return typeof g?.[name] === 'string' ? (g[name] as string) : '';
}

function PhoneView({ label, value }: { label: string; value: string }) {
  return (
    <div className="arm-phone">
      <div className="arm-phone__icons">
        <button type="button" aria-label={`Позвонить: ${label}`} disabled title="Исходящий звонок — п. 1.4"><Icon name="phone" size="sm" /></button>
        <button type="button" aria-label={`SMS: ${label}`} disabled title="СМС заявителю — п. 1.4"><Icon name="sms" size="sm" /></button>
      </div>
      <div className="arm-phone__field">
        <div className="arm-phone__label">{label}</div>
        <div className="arm-phone__input arm112v-phone">{value}</div>
      </div>
    </div>
  );
}

/** Строка ввода отработки (image87): служба, куда звонили, телефон, кто принял, суть сообщения, ✓. */
function WorkoutForm({ services, phoneOf, onAdd, busy }: {
  services: CardServiceView[]; phoneOf: (code: string) => string; onAdd: (b: WorkoutBody) => Promise<unknown>; busy: boolean;
}) {
  const empty: WorkoutBody = { service_code: services[0]?.code ?? null, target: '', called_to: '', phone: services[0] ? phoneOf(services[0].code) : '', receiver: '', message: '' };
  const [w, setW] = useState<WorkoutBody>(empty);
  const [error, setError] = useState('');
  const set = (patch: Partial<WorkoutBody>) => setW((x) => ({ ...x, ...patch }));
  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    if (!w.message.trim()) { setError('Укажите суть сообщения'); return; }
    if (!w.service_code && !w.target.trim()) { setError('Укажите, куда звонили'); return; }
    setError('');
    onAdd({ ...w, target: w.service_code ? '' : w.target.trim() }).then(() => setW(empty), (err: Error) => setError(err.message));
  };
  const now = new Date();
  return (
    <form className="arm112v-wk arm112v-wk--new" onSubmit={submit}>
      <div className="arm112v-wk__op"><Icon name="close" size="sm" /></div>
      <div>{fmtShort(now)} <b>{hhmm(now)}</b></div>
      <select className="arm112v-input" aria-label="Служба" value={w.service_code ?? ''}
        onChange={(e) => { const code = e.target.value || null; set({ service_code: code, phone: code ? phoneOf(code) : '' }); }}>
        {services.map((s) => <option key={s.code} value={s.code}>{s.short}</option>)}
        <option value="">другой адресат…</option>
      </select>
      <input className="arm112v-input" aria-label="Куда звонили" placeholder="куда"
        value={w.service_code ? w.called_to : w.target} onChange={(e) => (w.service_code ? set({ called_to: e.target.value }) : set({ target: e.target.value }))} />
      <input className="arm112v-input" aria-label="Телефон" placeholder="телефон" value={w.phone} onChange={(e) => set({ phone: e.target.value })} />
      <span className="arm112v-wk__call" title="Исходящий вызов — п. 1.4"><Icon name="phone" size="sm" /></span>
      <input className="arm112v-input" aria-label="Кто принял" placeholder="кто принял" value={w.receiver} onChange={(e) => set({ receiver: e.target.value })} />
      <input id="workout-message" className="arm112v-input" aria-label="Суть сообщения" placeholder="суть сообщения" value={w.message} onChange={(e) => set({ message: e.target.value })} />
      <button type="submit" className="arm112v-wk__ok" aria-label="Сохранить отработку (Enter)" disabled={busy}><Icon name="check" size="sm" /></button>
      {error && <div className="arm112v-wk__err" role="alert">{error}</div>}
    </form>
  );
}

function AppendForm({ view, busy, onSave, onCancel }: {
  view: CardView; busy: boolean; onSave: (fields: Record<string, string>, description: string, victims: number | null) => void; onCancel: () => void;
}) {
  const emptyFields = APPENDABLE.filter((f) => !valueAt(view.data, f.key));
  const [fields, setFields] = useState<Record<string, string>>({});
  const [text, setText] = useState('');
  const [victims, setVictims] = useState(String(view.data.victims?.count ?? 0));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const n = Number(victims);
    onSave(fields, text, Number.isFinite(n) && n !== (view.data.victims?.count ?? 0) ? n : null);
  };
  return (
    <form className="arm-panel arm112v-append" onSubmit={submit}>
      <div className="arm-panel__label"><b>Дополнение карточки</b> — только пустые поля, описание и пострадавшие</div>
      <div className="arm112-grid arm112-grid--3">
        {emptyFields.map((f) => (
          <label key={f.key} className="arm-field">
            <span className="arm-field__label">{f.label}:</span>
            <input className="arm-field__input" value={fields[f.key] ?? ''} onChange={(e) => setFields({ ...fields, [f.key]: e.target.value })} />
          </label>
        ))}
        <label className="arm-field">
          <span className="arm-field__label">Пострадавшие, количество:</span>
          <input className="arm-field__input" inputMode="numeric" value={victims} onChange={(e) => setVictims(e.target.value.replace(/\D/g, ''))} />
        </label>
      </div>
      <label className="arm-field" style={{ marginTop: 10 }}>
        <span className="arm-field__label">Дописать в описание:</span>
        <textarea id="append-description" className="arm112-textarea" rows={2} value={text} onChange={(e) => setText(e.target.value)} />
      </label>
      <div className="arm112-modal__btns" style={{ marginTop: 12 }}>
        <button type="submit" className="arm112-btn arm112-btn--primary" disabled={busy}>сохранить дополнение</button>
        <button type="button" className="arm112-btn" onClick={onCancel}>отмена</button>
      </div>
    </form>
  );
}

function ReturnModal({ busy, onConfirm, onClose }: { busy: boolean; onConfirm: (comment: string) => void; onClose: () => void }) {
  const [comment, setComment] = useState('');
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => ref.current?.focus(), []);
  return (
    <div className="arm112-modalwrap" role="dialog" aria-modal="true" aria-label="Вернуть на доработку">
      <div className="arm-overlay" onClick={onClose} />
      <div className="arm112-modal">
        <h2>Вернуть на доработку</h2>
        <label className="arm-field">
          <span className="arm-field__label">Что исправить (комментарий обучающемуся):</span>
          <textarea ref={ref} className="arm112-textarea" rows={3} value={comment} onChange={(e) => setComment(e.target.value)} />
        </label>
        <div className="arm112-modal__btns" style={{ marginTop: 16 }}>
          <button type="button" className="arm112-btn arm112-btn--primary" disabled={busy} onClick={() => onConfirm(comment)}>вернуть на доработку</button>
          <button type="button" className="arm112-btn" onClick={onClose}>отмена</button>
        </div>
      </div>
    </div>
  );
}

/** Режим АРМ ДДС (п. 2.2): та же карточка только для чтения, своя служба — с карандашом и строкой статуса. */
export interface DdsMode {
  service: string;
  next: string[];
  busy: boolean;
  onStatus: (b: ServiceStatusBody) => Promise<unknown>;
  onClose: () => void;
}

/** Строка «Статус ▾ · Номер наряда · Комментарий · ✓ ✕» (dds/image8–9): в списке — только доступные переходы. */
function DdsStatusEditor({ next, busy, lastOrderNo, onSave, onCancel }: {
  next: string[]; busy: boolean; lastOrderNo: string; onSave: (b: ServiceStatusBody) => Promise<unknown>; onCancel: () => void;
}) {
  const [status, setStatus] = useState(next.length === 1 ? next[0] : '');
  const [orderNo, setOrderNo] = useState(lastOrderNo);
  const [comment, setComment] = useState('');
  const [error, setError] = useState('');
  const ref = useRef<HTMLSelectElement>(null);
  useEffect(() => ref.current?.focus(), []);
  const save = () => {
    if (!status) { setError('Выберите статус'); return; }
    setError('');
    onSave({ status, order_no: orderNo, comment }).then(onCancel, (e: Error) => setError(e.message));
  };
  return (
    <div className="arm-stateditor dds-editor" role="dialog" aria-label="Изменение статуса службы">
      <select ref={ref} className="arm-uline arm-uline--select" style={{ width: 260 }} value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Статус">
        <option value="" disabled>Статус</option>
        {next.map((st) => <option key={st} value={st}>{SERVICE_STATUS[st] ?? st}</option>)}
      </select>
      <input className="arm-uline" style={{ width: 160 }} placeholder="Номер наряда" value={orderNo} onChange={(e) => setOrderNo(e.target.value)} maxLength={32} />
      <input className="arm-uline u-grow" placeholder="Комментарий" value={comment} maxLength={500} onChange={(e) => setComment(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') save(); }} />
      <button type="button" className="arm-iconsq" aria-label="Сохранить статус" disabled={busy} onClick={save}><Icon name="check" size="sm" /></button>
      <button type="button" className="arm-iconsq" aria-label="Отмена" onClick={onCancel}><Icon name="close" size="sm" /></button>
      {error && <div className="dds-editor__err" role="alert">{error}</div>}
    </div>
  );
}

export function CardViewer({ view, me, dds }: { view: CardView; me: Me; dds?: DdsMode }) {
  const navigate = useNavigate();
  const actions = useCardActions(view.id);
  const cardTypes = useCardTypes();
  const statuses = useEnum('applicant_status');
  const catalog = useServices();
  const [mode, setMode] = useState<'view' | 'append'>('view');
  const [history, setHistory] = useState<string | null>(null);
  const [returning, setReturning] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);
  const [showMap, setShowMap] = useState(false);
  const [editor, setEditor] = useState(false);

  // «Просмотр карточки» — в аудит один раз за открытие экрана
  const viewed = useRef(false);
  useEffect(() => {
    if (viewed.current || dds) return; // в ДДС открытие фиксирует «Получена службой»
    viewed.current = true;
    markCardViewed(view.id).catch(() => undefined);
  }, [view.id, dds]);
  useEffect(() => {
    if (!banner) return;
    const t = setTimeout(() => setBanner(null), 8000);
    return () => clearTimeout(t);
  }, [banner]);

  const d = view.data;
  const isAuthor = !dds && view.author_id === me.user_id && me.permissions.includes(PERMISSIONS.trainingParticipate);
  const canCheck = !dds && me.permissions.includes(CARDS_CHECK);
  const open = !['checked', 'completed'].includes(view.status);
  const canWorked = isAuthor && view.status === 'registered';
  const canChecked = canCheck && view.status === 'worked';
  const canReturn = canCheck && ['worked', 'checked'].includes(view.status);
  const canEdit = isAuthor && open;

  const titles = useMemo(() => new Map((cardTypes.data ?? []).map((t) => [t.code, t.title])), [cardTypes.data]);
  const statusName = statuses.data?.find((s) => s.code === d.applicant?.status)?.name ?? '';
  const phoneOf = (code: string) => catalog.data?.find((s) => s.code === code)?.phone ?? '';
  const serviceName = (code: string | null) => view.services.find((s) => s.code === code)?.short ?? catalog.data?.find((s) => s.code === code)?.short ?? code ?? '';
  const fail = (e: Error) => setBanner(e.message);

  const saved = dt(view.saved_at);
  const operator = `${view.operator_number ?? ''}, АРМ ${view.arm_number ?? '—'}, ${view.author_name ? shortName(view.author_name) : ''}`;
  const victims = d.victims?.has ? (d.victims.count > 0 ? String(d.victims.count) : 'есть') : 'нет';
  const flagsSet = new Set(d.card_flags ?? []);
  // в ДДС своя служба — первой, чтобы плитка с карандашом была на виду
  const services = [...view.services].sort((a, b) =>
    Number(b.code === dds?.service) - Number(a.code === dds?.service) || Number(b.is_main) - Number(a.is_main));
  const ownService = dds ? view.services.find((s) => s.code === dds.service) : undefined;
  const lastOrderNo = [...(ownService?.history ?? [])].reverse().find((h) => h.order_no)?.order_no ?? '';
  const descriptionLines = (d.description ?? '').split('\n').filter(Boolean);
  const addressExtra = [
    d.address?.object && `объект: ${d.address.object}`,
    d.address?.flat && `кв./офис ${d.address.flat}`,
    d.address?.entrance && `подъезд ${d.address.entrance}`,
    d.address?.floor && `этаж ${d.address.floor}`,
    d.address?.code && `код ${d.address.code}`,
  ].filter(Boolean).join(', ');

  const worked = () => canWorked && actions.worked.mutate('', { onError: fail });
  const checked = () => canChecked && actions.checked.mutate('', { onError: fail });
  const toggleFlag = (key: 'emergency' | 'incident') => {
    if (!canEdit) return;
    const next = { emergency: view.is_emergency, incident: view.is_incident, [key]: !(key === 'emergency' ? view.is_emergency : view.is_incident) };
    actions.flags.mutate(next, { onError: fail });
  };
  const close = () => (dds ? dds.onClose() : navigate('/arm/112/journal'));

  const alt: HotkeyMap = returning || dds ? {} : {
    KeyS: worked, KeyY: checked, ...(canReturn && { KeyN: () => setReturning(true) }),
    KeyO: focusId('workout-message'),
  };
  const plain: HotkeyMap = dds ? {
    Escape: () => (editor ? setEditor(false) : history ? setHistory(null) : close()),
  } : returning ? { Escape: () => setReturning(false) } : {
    Escape: () => (history ? setHistory(null) : mode === 'append' ? setMode('view') : close()),
    F1: () => setMode('view'),
    ...(canEdit && { F2: () => setMode('append') }),
    ...(me.permissions.includes(PERMISSIONS.trainingParticipate) && { Insert: () => navigate('/arm/112') }),
  };
  const altHeld = useHotkeys(alt, plain);

  const historyService = services.find((s) => s.code === history);
  const tab = (s: CardServiceView) => {
    const mine = dds?.service === s.code;
    return (
      <ServiceTab key={s.code} name={s.short} main={s.is_main} noIntegration={!s.integrated} mine={mine}
        status={`${s.status_at ? hhmm(new Date(s.status_at)) : ''} ${SERVICE_STATUS[s.status] ?? s.status}`}
        onOpen={() => { setEditor(false); setHistory(history === s.code ? null : s.code); }}
        onEdit={mine && dds && dds.next.length ? () => { setHistory(null); setEditor(true); } : undefined} />
    );
  };
  const statusLine = [
    `Статус: ${CARD_STATUS[view.display_status] ?? view.display_status}`,
    view.worked_at && `отработана ${fmtFull(new Date(view.worked_at))}`,
    view.checked_at && `проверена ${fmtFull(new Date(view.checked_at))}${view.checked_by_name ? ` (${shortName(view.checked_by_name)})` : ''}`,
  ].filter(Boolean).join(' · ');

  return (
    <div className={`arm112 arm112-saved arm112v${altHeld ? ' arm112--alt' : ''}`}>
      <div className="arm112__top">
        <CallControl title="Отключение" recordsDisabled />
        <PhoneView label="АОН" value={d.phones?.aon ?? ''} />
        <PhoneView label="предоставленный" value={d.phones?.provided ?? ''} />
        <PhoneView label="телефон на место" value={d.phones?.on_site ?? ''} />
        <div className="arm-idbox" style={{ width: 235 }}>
          <div className="arm-idbox__title">Происшествие {view.number}</div>
          <div className="arm-idbox__meta">{saved ? `Сохр. ${fmtFull(saved)}` : ''}<br />Опер. {operator}</div>
        </div>
        <div className="arm112-rel" style={{ display: 'flex' }}>
          <Hint k="Shift+F1/F2" />
          <IncidentActions onView={() => setMode('view')} onAppend={canEdit ? () => setMode('append') : undefined} />
        </div>
      </div>

      <div className="arm112__body arm112v__body">
        <div className="arm-panel arm112v-applicant">
          <span className="arm112v-small">ФИО заявителя</span>
          <b>{d.applicant?.name}</b>{statusName && <span className="arm112v-muted">{statusName}</span>}
          {d.applicant?.foreign_language && <span className="arm112v-muted">вызов на иностранном языке</span>}
        </div>
        <div className="arm112__row2">
          <div className="arm-panel arm-flags__text arm112v-flags">
            <span>Пострадавшие: {victims}</span>
            <span>Отказ от скорой: {flagsSet.has('victims_not_on_site') || d.flags?.refusal_103 ? 'да' : 'нет'}</span>
            <span>Заблокированные: {flagsSet.has('no_access') ? 'да' : 'нет'}</span>
          </div>
          <div className="arm-panel arm-flags__btns">
            <button type="button" className="arm-flagbtn" aria-pressed={view.is_emergency} disabled={!canEdit || actions.flags.isPending} onClick={() => toggleFlag('emergency')} title="Чрезвычайная ситуация">ЧС <Icon name="bolt" size="xs" /></button>
            <button type="button" className="arm-flagbtn arm-flagbtn--chp" aria-pressed={view.is_incident} disabled={!canEdit || actions.flags.isPending} onClick={() => toggleFlag('incident')} title="Чрезвычайное происшествие">ЧП <Icon name="warning" size="xs" /></button>
            <button type="button" className="arm-roundbtn" aria-label="Дополнение (Shift+F2)" disabled={!canEdit} onClick={() => setMode('append')}><Icon name="edit" size="sm" /></button>
          </div>
        </div>

        <div className="arm112__col">
          <div className="arm-panel arm112v-address">
            <div className="arm112v-address__line">
              <b>{view.address_line ?? 'адрес не указан'}</b>
              <button type="button" className="arm112-mapbtn" aria-label="Карта" title="Карта" aria-pressed={showMap} onClick={() => setShowMap(!showMap)}>
                <Icon name="place" size="sm" />
              </button>
            </div>
            {addressExtra && <div className="arm112v-muted">{addressExtra}</div>}
            {d.address?.descriptive && <div className="arm112v-muted">{d.address.descriptive}</div>}
          </div>
          {mode === 'append' ? (
            <AppendForm
              view={view} busy={actions.append.isPending} onCancel={() => setMode('view')}
              onSave={(fields, description, count) => actions.append.mutate(
                { fields, description_add: description, victims_count: count },
                { onSuccess: () => setMode('view'), onError: fail },
              )}
            />
          ) : (
            <div className="arm-panel arm-panel--fill arm112v-desc">
              {descriptionLines.length ? (
                <>
                  <div className="arm112v-desc__meta">{saved ? `${saved.toLocaleDateString('ru-RU')} ${hhmmss(saved)}` : ''}  {view.operator_number ?? ''} {view.author_name ? shortName(view.author_name) : ''}</div>
                  {descriptionLines.map((line, i) => <div key={i}>{line}</div>)}
                </>
              ) : <span className="arm112v-muted">Описание со слов заявителя</span>}
            </div>
          )}
        </div>

        <div className="arm112__col arm112__scroll">
          {d.flags?.no_contact || d.flags?.call_dropped ? (
            <div className="arm-panel"><b>{d.flags?.no_contact ? '<Нет контакта>' : '<Срыв связи>'}</b> — карточка сохранена пустой</div>
          ) : (
            (d.card_types ?? []).map((ct) => {
              const answers = Object.entries(d.questionnaire?.[ct] ?? {});
              const path = answers.filter(([k]) => k.startsWith('Признак')).map(([, v]) => v);
              const rest = answers.filter(([k]) => !k.startsWith('Признак')).map(([k, v]) => (v === 'Да' ? k : v === 'Нет' ? `${k}: нет` : `${k}: ${v}`));
              return (
                <div key={ct} className="arm-q">
                  <div className="arm-q__head"><span className="arm112v-qtitle">{/^\d{3}$/.test(ct) ? `Происшествие ${ct}` : `П: ${titles.get(ct) ?? ct}`}</span></div>
                  {(path.length > 0 || rest.length > 0) && <div className="arm112v-answers">{[...path, ...rest].join('. ')}.</div>}
                </div>
              );
            })
          )}
          {view.incident_types.length > 0 && (
            <div className="arm-panel arm112v-class">Класс.: <b>{view.incident_types.map((t) => t.final_type ?? t.code).join('; ')};</b></div>
          )}
          {!dds && <div className="arm-panel arm112v-class arm112v-muted" data-testid="card-status">{statusLine}</div>}
          {!dds && view.status !== 'draft' && (view.author_id === me.user_id || me.permissions.includes(CARDS_CHECK)) && (
            <AssessmentPanel cardId={view.id} role="112" auto={view.author_id === me.user_id} />
          )}
          {dds && ownService && ownService.status !== 'added' && ownService.status !== 'received' && (
            <AssessmentPanel cardId={view.id} role="dds" service={dds.service} auto={false} />
          )}
        </div>
      </div>

      {showMap && <AddressMap lat={d.address?.lat ?? null} lon={d.address?.lon ?? null} district={d.address?.district ?? null} readOnly onClose={() => setShowMap(false)} />}
      {banner && <div className="arm112-banner" role="alert" onClick={() => setBanner(null)}><b>Действие не выполнено</b><ul><li>{banner}</li></ul></div>}
      {view.rework && (
        <div className="arm112-rework" role="status">
          <b>Возвращена на доработку</b>
          {[view.rework.by && shortName(view.rework.by), view.rework.at && fmtFull(new Date(view.rework.at))].filter(Boolean).join(', ').replace(/^(.+)$/, ' ($1)')}
          {view.rework.comment ? `: ${view.rework.comment}` : ''}
        </div>
      )}

      {!dds && <div className="arm112v-workouts arm112-rel">
        <Hint k="Alt+O" />
        <div className="arm112v-wk arm112v-wk--head">
          <div>Опер.</div><div>Дата и время</div><div>Служба</div><div>Куда звонили</div><div>Телефон</div><div /><div>ФИО</div><div>Суть сообщения</div><div />
        </div>
        {view.workouts.map((w) => {
          const at = new Date(w.at);
          return (
            <div key={w.id} className="arm112v-wk arm112v-wk--row">
              <div className="arm112v-wk__op">{w.operator_number ?? ''}</div>
              <div>{fmtShort(at)} <b>{hhmm(at)}</b></div>
              <div>{w.service_code ? serviceName(w.service_code) : w.target}</div>
              <div>{w.called_to}</div>
              <div>{w.phone}</div>
              <div />
              <div>{w.receiver}</div>
              <div className="arm112v-wk__msg">{w.message}</div>
              <div />
            </div>
          );
        })}
        {canEdit && (
          <WorkoutForm key={`${view.workouts.length}:${catalog.data ? 1 : 0}`} services={services} phoneOf={phoneOf} busy={actions.workout.isPending}
            onAdd={(b) => actions.workout.mutateAsync(b)} />
        )}
      </div>}

      <ServiceBar
        variant="112"
        expanded={expanded}
        onToggleExpand={services.length > 6 ? () => setExpanded(!expanded) : undefined}
        stack={services.length > 6 ? services.slice(6).map(tab) : undefined}
        overlay={(editor && dds) ? (
          <DdsStatusEditor next={dds.next} busy={dds.busy} lastOrderNo={lastOrderNo} onSave={dds.onStatus} onCancel={() => setEditor(false)} />
        ) : historyService && (
          <StatusHistory
            service={historyService.short} onClose={() => setHistory(null)} style={{ left: 90, bottom: 'calc(100% + 4px)' }}
            rows={historyService.history.map((h) => ({
              operator: h.operator ? `оп. ${h.operator}` : 'оп. 0',
              at: h.at ? `${new Date(h.at).toLocaleDateString('ru-RU')} ${hhmmss(new Date(h.at))}` : '',
              status: SERVICE_STATUS[h.status] ?? h.status,
              comment: [h.order_no && `наряд ${h.order_no}`, h.comment].filter(Boolean).join(' · ') || undefined,
            }))}
          />
        )}
        end={(
          <>
            {canWorked && <span className="arm112-rel"><Hint k="Alt+S" /><button type="button" className="arm-savebtn" disabled={actions.worked.isPending} onClick={worked}>отработана</button></span>}
            {canChecked && <span className="arm112-rel"><Hint k="Alt+Y" /><button type="button" className="arm-savebtn" disabled={actions.checked.isPending} onClick={checked}>Проверена</button></span>}
            {canReturn && <span className="arm112-rel"><Hint k="Alt+N" /><button type="button" className="arm-savebtn arm112v-return" onClick={() => setReturning(true)}>Вернуть на доработку</button></span>}
            {dds && ownService && dds.next.length > 0 && (
              <button type="button" className="arm-savebtn" onClick={() => { setHistory(null); setEditor(true); }}>изменить статус</button>
            )}
            <button type="button" className="arm-sqbtn" disabled title="Связи карточек — п. 1.6" aria-label="Связи"><Icon name="link" /></button>
            <button type="button" className="arm-sqbtn" disabled title="Напоминание — появится в следующих пунктах плана" aria-label="Напоминание"><Icon name="timer" /></button>
            <button type="button" className="arm-sqbtn" disabled title="Важное происшествие — появится в следующих пунктах плана" aria-label="Важное происшествие"><Icon name="bell" /></button>
            <SquareButton icon="close" label="Закрыть карточку (Esc)" onClick={close} />
          </>
        )}
      >
        {services.slice(0, 6).map(tab)}
      </ServiceBar>

      {returning && (
        <ReturnModal busy={actions.returned.isPending} onClose={() => setReturning(false)}
          onConfirm={(comment) => actions.returned.mutate(comment, { onSuccess: () => setReturning(false), onError: (e) => { setReturning(false); fail(e); } })} />
      )}
    </div>
  );
}
