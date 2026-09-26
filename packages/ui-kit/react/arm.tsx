/* Компоненты АРМ-скина: копия АРМ-112 / АРМ-ДДС + учебные надстройки (тренажёрная полоса, софтфон, очередь). */
import type { CSSProperties, InputHTMLAttributes, ReactNode } from 'react';
import { Icon, type IconName } from './Icon';
import { StatusPill } from './primitives';
import { cx, formatMmSs, formatTimer, normStatus } from './util';

/* ======================= Каркас ======================= */
export function ArmApp({ trainingBar, dock, children }: { trainingBar?: ReactNode; dock?: ReactNode; children: ReactNode }) {
  return (
    <div className="arm-app">
      {trainingBar}
      <div className={cx('arm-body', !dock && 'arm-body--full')}>
        {children}
        {dock}
      </div>
    </div>
  );
}

export interface TrainingBarProps {
  lesson: string;
  role: string;
  progress: string;
  /** Учебное время «11:24:26» */
  simTime: string;
  speed: number;
  onHelp?: () => void;
  onHint?: () => void;
}
export function TrainingBar({ lesson, role, progress, simTime, speed, onHelp, onHint }: TrainingBarProps) {
  const [hm, sec] = [simTime.slice(0, 5), simTime.slice(6, 8)];
  return (
    <header className="arm-trainbar">
      <span className="arm-trainbar__badge">Тренажёр</span>
      <span className="arm-trainbar__meta">Занятие: <b>{lesson}</b></span>
      <span className="arm-trainbar__meta">Роль: <b>{role}</b></span>
      <span className="arm-trainbar__meta">Карточка <b>{progress}</b></span>
      <span className="u-grow" />
      <span className="arm-trainbar__meta">Учебное время</span>
      <span className="arm-trainbar__clock">
        {hm}{sec && <span className="t-sec">{sec}</span>}<span className="arm-trainbar__speed">×{speed}</span>
      </span>
      <button type="button" className="arm-trainbar__btn" onClick={onHelp}><Icon name="description" size="sm" />Справка F1</button>
      <button type="button" className="arm-trainbar__btn" onClick={onHint}><Icon name="help" size="sm" />Подсказка</button>
    </header>
  );
}

/* ======================= Верхняя полоса карточки ======================= */
export function CallControl({ title = 'Отключение', recordsDisabled = false, onHangup, onRecords, onSms }: {
  title?: string; recordsDisabled?: boolean; onHangup?: () => void; onRecords?: () => void; onSms?: () => void;
}) {
  return (
    <div className="arm-callctl">
      <button type="button" className="arm-callctl__hang" style={{ border: 0, background: 'none' }} aria-label="Завершить вызов" onClick={onHangup}>
        <Icon name="call_end" size="lg" />
      </button>
      <div className="arm-callctl__main">
        <div className="arm-callctl__title">{title}</div>
        <div className="arm-callctl__btns">
          <button type="button" className={cx('arm-minibtn', recordsDisabled && 'arm-minibtn--disabled')} onClick={onRecords} disabled={recordsDisabled}>записи звонков</button>
          <button type="button" className="arm-minibtn" onClick={onSms}>список SMS</button>
        </div>
      </div>
    </div>
  );
}

export interface PhoneFieldProps { label: string; value?: string; active?: boolean; onCall?: () => void; onSms?: () => void; }
export function PhoneField({ label, value, active, onCall, onSms }: PhoneFieldProps) {
  return (
    <div className={cx('arm-phone', active && 'arm-phone--active')}>
      <div className="arm-phone__icons">
        <button type="button" aria-label={`Позвонить: ${label}`} onClick={onCall}><Icon name="phone" size="sm" /></button>
        <button type="button" aria-label={`SMS: ${label}`} onClick={onSms}><Icon name="sms" size="sm" /></button>
      </div>
      <div className="arm-phone__field">
        <div className="arm-phone__label">{label}</div>
        <div className={cx('arm-phone__value', !value && 'arm-phone__value--empty')}>{value || '—'}</div>
      </div>
    </div>
  );
}

export function IncidentIdBox({ number, savedAt, operator }: { number: string; savedAt: string; operator: string }) {
  return (
    <div className="arm-idbox">
      <div className="arm-idbox__title">Происшествие {number}</div>
      <div className="arm-idbox__meta">Сохр. {savedAt}<br />Опер. {operator}</div>
    </div>
  );
}

export function IncidentActions({ onView, onAppend }: { onView?: () => void; onAppend?: () => void }) {
  return (
    <div className="arm-idbtns">
      <button type="button" className="arm-idbtn arm-idbtn--view" onClick={onView}>просмотр</button>
      <button type="button" className="arm-idbtn" onClick={onAppend}>дополнение</button>
    </div>
  );
}

/** Таймер карточки 112: краснеет при превышении норматива (как в реальном АРМ). */
export function CardTimer({ seconds, normSeconds }: { seconds: number; normSeconds: number }) {
  const over = seconds > normSeconds;
  return (
    <div className={cx('arm-timer', over && 'arm-timer--over')} role="timer" aria-label={`Время заполнения ${formatTimer(seconds)}${over ? ', норматив превышен' : ''}`}>
      <span className="arm-timer__value">{formatTimer(seconds)}</span>
      <span className="arm-timer__units"><span>минут</span><span>секунд</span></span>
    </div>
  );
}

/* ======================= Поля и чипы АРМ-112 ======================= */
export function ArmField({ label, ...input }: { label?: string } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="arm-field">
      <span className="arm-field__label">{label ?? ' '}</span>
      <input className="arm-field__input" {...input} />
    </label>
  );
}

export function Chip({ selected = false, flat = false, children, onClick }: { selected?: boolean; flat?: boolean; children: ReactNode; onClick?: () => void }) {
  return (
    <button type="button" className={cx('arm-chip', flat && 'arm-chip--flat')} aria-pressed={selected} onClick={onClick}>
      {children}
    </button>
  );
}

export function BigButton({ alert = false, children, onClick }: { alert?: boolean; children: ReactNode; onClick?: () => void }) {
  return <button type="button" className={cx('arm-bigbtn', alert && 'arm-bigbtn--alert')} onClick={onClick}>{children}</button>;
}

/** Опросная карта (например «Происшествие 101») */
export function Questionnaire({ title, onClose, children }: { title: string; onClose?: () => void; children: ReactNode }) {
  return (
    <section className="arm-q">
      <div className="arm-q__head">
        <span>{title}</span>
        <button type="button" onClick={onClose} aria-label="Убрать тип" style={{ border: 0, background: 'none', color: 'inherit', display: 'flex', padding: 0 }}>
          <Icon name="close" size="sm" />
        </button>
      </div>
      {children}
    </section>
  );
}

export interface QuestionRowProps {
  label: string;
  options: string[];
  selected: string[];
  onToggle: (option: string) => void;
}
export function QuestionRow({ label, options, selected, onToggle }: QuestionRowProps) {
  return (
    <div className="arm-q__row">
      <span className="arm-q__label">{label}</span>
      <span className="arm-chips arm-chips--tight">
        {options.map((o) => <Chip key={o} selected={selected.includes(o)} onClick={() => onToggle(o)}>{o}</Chip>)}
      </span>
    </div>
  );
}

/* ======================= Панель служб ======================= */
export interface ServiceTabProps {
  name: string;
  /** «11:14 Добавлена» (ДДС) */
  status?: string;
  /** Основная служба для типа — подчёркивание */
  main?: boolean;
  /** Служба без интеграции (серый) */
  noIntegration?: boolean;
  /** Своя служба обучающегося-ДДС (синий, с карандашом) */
  mine?: boolean;
  variant?: 'dds' | '112';
  onOpen?: () => void;
  onEdit?: () => void;
  onRemove?: () => void;
}
export function ServiceTab({ name, status, main, noIntegration, mine, variant = 'dds', onOpen, onEdit, onRemove }: ServiceTabProps) {
  const cls = cx('arm-svc', main && 'arm-svc--main', noIntegration && 'arm-svc--nointegr', mine && 'arm-svc--mine');
  if (variant === '112') {
    return (
      <span className={cls}>
        <Icon name="phone" size="xs" className="arm-svc__phone" />
        {onRemove && <button type="button" className="arm-svc__x" onClick={onRemove} aria-label={`Убрать ${name}`} style={{ border: 0, background: 'none', color: 'inherit', padding: 0, display: 'flex' }}><Icon name="close" size="xs" /></button>}
        <span className="arm-svc__name u-ellipsis">{name}</span>
      </span>
    );
  }
  return (
    <div className={cls} role="button" tabIndex={0} onClick={onOpen} onKeyDown={(e) => e.key === 'Enter' && onOpen?.()}>
      {mine ? (
        <span className="arm-svc__tools">
          <span className="arm-svc__toggle"><Icon name="expand_more" size="xs" /></span>
          <button type="button" aria-label="Изменить статус" onClick={(e) => { e.stopPropagation(); onEdit?.(); }}><Icon name="edit" size="xs" /></button>
        </span>
      ) : (
        <Icon name="expand_less" size="xs" className="arm-svc__caret" />
      )}
      <span className="arm-svc__name u-ellipsis" style={mine ? { marginTop: 14 } : undefined}>{name}</span>
      {status && <span className="arm-svc__status" title={status}>{status}</span>}
    </div>
  );
}

export interface ServiceBarProps {
  variant?: 'dds' | '112';
  children: ReactNode;
  /** Второй ряд служб (разворачивается) */
  stack?: ReactNode;
  /** Поповер истории статусов и т.п. */
  overlay?: ReactNode;
  /** Правая часть: сохранить, связь, будильник, ✕ … */
  end?: ReactNode;
  /** Кнопки сразу после служб и ⇕ (АРМ-112: «+» — добавить службу) */
  actions?: ReactNode;
  expanded?: boolean;
  onToggleExpand?: () => void;
}
export function ServiceBar({ variant = 'dds', children, stack, overlay, end, actions, expanded, onToggleExpand }: ServiceBarProps) {
  return (
    <footer className={cx('arm-svcbar', variant === '112' && 'arm-svcbar--112')}>
      {overlay}
      {expanded && stack && <div className="arm-svcstack">{stack}</div>}
      <div className="arm-svcbar__label">Службы:</div>
      <div className="arm-svcbar__tabs">
        {children}
        {onToggleExpand && (
          <div style={{ display: 'flex', alignItems: 'center', paddingLeft: 16 }}>
            <button type="button" className="arm-sqbtn" onClick={onToggleExpand} aria-label={expanded ? 'Свернуть ряд служб' : 'Развернуть ряд служб'}>
              <Icon name={expanded ? 'unfold_less' : 'unfold_more'} />
            </button>
          </div>
        )}
        {actions}
      </div>
      {end && <div className="arm-svcbar__end">{end}</div>}
    </footer>
  );
}

export function SquareButton({ icon, label, onClick }: { icon: IconName; label: string; onClick?: () => void }) {
  return <button type="button" className="arm-sqbtn" aria-label={label} title={label} onClick={onClick}><Icon name={icon} /></button>;
}

/* ======================= Статусы ДДС ======================= */
export const DDS_STATUSES = [
  'Принята', 'Не принята', 'Начало реагирования', 'Прибытие', 'Проведение работ', 'Работы завершены', 'Отказ от выполнения работ',
] as const;
export type DdsStatus = typeof DDS_STATUSES[number];

export interface StatusHistoryRow { operator: string; at: string; status: string; comment?: string; }
export function StatusHistory({ service, rows, onClose, style }: { service: string; rows: StatusHistoryRow[]; onClose?: () => void; style?: CSSProperties }) {
  return (
    <div className="arm-history" style={style} role="dialog" aria-label={`История статусов: ${service}`}>
      <div className="arm-history__head">
        <span>{service}</span>
        <button type="button" onClick={onClose} aria-label="Закрыть"><Icon name="close" size="sm" /></button>
      </div>
      <div className="arm-history__rows">
        {rows.map((r, i) => (
          <div className="arm-history__row" key={i}>
            <span className="arm-history__op">{r.operator}</span>
            <Icon name="chevron_right" size="xs" />
            <span className="arm-history__status">{r.at} <b>{r.status}</b></span>
            {r.comment ? <Icon name="chevron_right" size="xs" /> : <span />}
            <span>{r.comment}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export interface StatusEditorProps {
  status: DdsStatus | '';
  orderNo: string;
  comment: string;
  onStatus: (s: DdsStatus) => void;
  onOrderNo: (v: string) => void;
  onComment: (v: string) => void;
  onSave: () => void;
  onCancel: () => void;
  style?: CSSProperties;
}
/** Строка ввода статуса (Статус ▾ · Номер наряда · Комментарий · ✓ ✕). Эмулятор не блокирует «неверные» статусы — их ловит оценщик. */
export function StatusEditor({ status, orderNo, comment, onStatus, onOrderNo, onComment, onSave, onCancel, style }: StatusEditorProps) {
  return (
    <div className="arm-stateditor" style={style} role="dialog" aria-label="Изменение статуса службы">
      <select className="arm-uline arm-uline--select" style={{ width: 260 }} value={status} onChange={(e) => onStatus(e.target.value as DdsStatus)} aria-label="Статус">
        <option value="" disabled>Статус</option>
        {DDS_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
      </select>
      <input className="arm-uline" style={{ width: 160 }} placeholder="Номер наряда" value={orderNo} onChange={(e) => onOrderNo(e.target.value)} />
      <input className="arm-uline u-grow" placeholder="Комментарий" value={comment} onChange={(e) => onComment(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') onSave(); if (e.key === 'Escape') onCancel(); }} />
      <button type="button" className="arm-iconsq" aria-label="Сохранить" onClick={onSave}><Icon name="check" size="sm" /></button>
      <button type="button" className="arm-iconsq" aria-label="Отмена" onClick={onCancel}><Icon name="close" size="sm" /></button>
    </div>
  );
}

/* ======================= Журнал происшествий ДДС ======================= */
export interface JournalIncident {
  number: string; date: string; time: string; type: string; victims: boolean; address: string;
  serviceStatus: string; description: string; descMeta: string; operatorCell?: string; arm?: string;
  /** Учебная надстройка: сколько карточка ждёт реакции */
  waitSec?: number;
  isNew?: boolean;
}
export function JournalRow({ inc, normSec = 30, onOpen }: { inc: JournalIncident; normSec?: number; onOpen?: () => void }) {
  const [hm, sec] = inc.time.split(/:(?=\d{2}$)/);
  const st = inc.waitSec != null ? normStatus(inc.waitSec, normSec) : null;
  return (
    <div className="arm-jitem">
      <div className={cx('arm-jgrid arm-jrow', inc.isNew && 'arm-jrow--new')} onDoubleClick={onOpen}>
        <div><Icon name="expand_more" size="sm" /></div>
        <div className="c-slate"><Icon name="bookmark" size="sm" /></div>
        <div><Icon name="bolt" size="sm" /></div>
        <div><Icon name="timer" size="sm" /></div>
        <div className="c-wine">{inc.operatorCell ?? '0'}</div>
        <div className="c-slate">{inc.arm ?? '4'}</div>
        <div>{inc.number}</div>
        <div>{inc.date}</div>
        <div className="c-time">{hm}<span className="t-sec">{sec}</span></div>
        <div className="c-type">{inc.type}</div>
        <div className="c-slate">{inc.victims ? 'Есть' : 'Нет'}</div>
        <div className="c-addr">{inc.address}</div>
        <div className="c-status">{inc.serviceStatus}</div>
        <div className="c-slate">
          {st && <StatusPill surface="dark" status={st}>{st === 'ok' ? 'в норме' : formatMmSs(inc.waitSec!)}</StatusPill>}
        </div>
        <div className="c-slate"><button type="button" onClick={onOpen} aria-label="Открыть карточку" style={{ border: 0, background: 'none', color: 'inherit', display: 'flex' }}><Icon name="clipboard" size="sm" /></button></div>
      </div>
      <div className="arm-jdesc">
        <span className="arm-jdesc__label">Описание:</span>
        <span className="arm-jdesc__meta">{inc.descMeta}</span>
        <span className="arm-jdesc__text">{inc.description}</span>
      </div>
    </div>
  );
}

/* ======================= Учебный док: софтфон и очередь ======================= */
export function Dock({ children }: { children: ReactNode }) {
  return <aside className="arm-dock" aria-label="IP-телефон и очередь карточек">{children}</aside>;
}
export function DockSection({ title, aside, grow, children }: { title?: ReactNode; aside?: ReactNode; grow?: boolean; children: ReactNode }) {
  return (
    <div className={cx('arm-dock__section', grow && 'arm-dock__section--grow')}>
      {title && <div className="arm-dock__title"><span>{title}</span>{aside}</div>}
      {children}
    </div>
  );
}

export function IncomingCall({ who, sub, onAnswer, onReject }: { who: string; sub: string; onAnswer: () => void; onReject: () => void }) {
  return (
    <div className="arm-ring" role="alert">
      <Icon name="phone" size="lg" className="arm-ring__icon" />
      <div className="u-grow">
        <div className="arm-ring__who">{who}</div>
        <div className="arm-ring__sub">{sub}</div>
      </div>
      <button type="button" className="arm-ring__btn" onClick={onAnswer}>Ответить</button>
      <button type="button" className="arm-ring__btn arm-ring__btn--ghost" onClick={onReject} aria-label="Отклонить"><Icon name="close" size="sm" /></button>
    </div>
  );
}

export type LineState = 'idle' | 'busy' | 'hold';
export function LineKeys({ lines }: { lines: { label: string; state: LineState }[] }) {
  return (
    <div className="arm-linekeys">
      {lines.map((l) => (
        <button key={l.label} type="button" className={cx('arm-linekey', l.state !== 'idle' && `arm-linekey--${l.state}`)}>
          <span className="arm-linekey__led" />{l.label}
        </button>
      ))}
    </div>
  );
}

export interface TranscriptMessage { from: 'me' | 'them' | 'sys'; who?: string; text: string; }
export function Transcript({ messages }: { messages: TranscriptMessage[] }) {
  return (
    <div className="arm-transcript u-scroll" aria-live="polite">
      {messages.map((m, i) => (
        <div key={i} className={cx('arm-msg', `arm-msg--${m.from}`)}>
          {m.who && m.from !== 'sys' && <span className="arm-msg__who">{m.who}</span>}
          {m.text}
        </div>
      ))}
    </div>
  );
}

export function Composer({ value, onChange, onSend, placeholder = 'Что вы говорите в трубку…' }: { value: string; onChange: (v: string) => void; onSend: () => void; placeholder?: string }) {
  return (
    <div className="arm-composer">
      <input type="text" value={value} placeholder={placeholder} aria-label="Реплика" onChange={(e) => onChange(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && onSend()} />
      <button type="button" className="arm-contact__call" aria-label="Отправить" onClick={onSend}><Icon name="send" size="sm" /></button>
    </div>
  );
}

export function Contact({ name, sub, onCall }: { name: string; sub: string; onCall: () => void }) {
  return (
    <div className="arm-contact">
      <div><div className="arm-contact__name">{name}</div><div className="arm-contact__sub">{sub}</div></div>
      <button type="button" className="arm-contact__call" aria-label={`Позвонить: ${name}`} onClick={onCall}><Icon name="phone" size="sm" /></button>
    </div>
  );
}

export interface QueueItemProps { title: string; sub: string; waitSec?: number; normSec?: number; active?: boolean; onSelect?: () => void; }
/** Карточка в очереди: таймер ожидания — статус норматива (иконка + подпись). */
export function QueueItem({ title, sub, waitSec, normSec = 30, active, onSelect }: QueueItemProps) {
  const st = active || waitSec == null ? 'ok' : normStatus(waitSec, normSec);
  const label = active ? 'в работе' : st === 'critical' ? `${formatMmSs(waitSec!)} · сверх нормы` : st === 'warn' ? `${formatMmSs(waitSec!)} · скоро норма` : formatMmSs(waitSec ?? 0);
  return (
    <div className={cx('arm-queue__item', active && 'arm-queue__item--active')} role="button" tabIndex={0} onClick={onSelect}>
      <span className="arm-queue__title">{title}</span>
      <StatusPill surface="dark" status={st}>{label}</StatusPill>
      <span className="arm-queue__sub">{sub}</span>
    </div>
  );
}
