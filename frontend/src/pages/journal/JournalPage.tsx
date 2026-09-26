/** «Список происшествий» АРМ-112 (п. 1.3): вид по img/instr/image57 и image113, шапка — как у стенда 2026 (dds/image2).
 *  Обучающийся видит свои карточки, преподаватель — все (сервер). Автообновление — опрос раз в 5 с. */
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon, IncomingCall } from '@smena112/ui-kit';
import { PERMISSIONS, useMe } from '../../shared/api/auth';
import { useCardTypes } from '../../shared/api/dictionaries';
import { CARD_STATUS, useJournal, useOpenCard, type JournalQuery, type JournalRow } from '../../shared/api/incidents';
import { endCall, startIncomingCall, type CallStarted } from '../../shared/api/training';
import { ArmTopBar } from '../../shared/ui/ArmTopBar';
import { ARM_MENU } from '../../shared/ui/armMenu';
import { useHotkeys } from '../card112/useHotkeys';

const PAGE_SIZES = [15, 30, 50, 100];
const pad = (n: number) => String(n).padStart(2, '0');
/** Фильтр «выберите что показывать»: статусы журнала (п. 1.3, §2). «Заполняется» — через «обращения в очереди». */
const FILTERS: { value: string; label: string; statuses: string[] }[] = [
  { value: '', label: 'все карточки', statuses: [] },
  { value: 'registered', label: 'Зарегистрирована', statuses: ['registered'] },
  { value: 'not_notified', label: 'Не оповещено', statuses: ['not_notified'] },
  { value: 'worked', label: 'Отработана', statuses: ['worked'] },
  { value: 'checked', label: 'Проверена', statuses: ['checked'] },
  { value: 'completed', label: 'пустые карточки', statuses: ['completed'] },
];
const NOT_DRAFT = ['registered', 'not_notified', 'worked', 'checked', 'completed'];

interface Draft { q: string; fromDate: string; toDate: string }
const EMPTY_DRAFT: Draft = { q: '', fromDate: '', toDate: '' };
const toIso = (date: string, end = false) => (date ? new Date(`${date}T${end ? '23:59:59.999' : '00:00:00'}`).toISOString() : '');

/** Переключатель как в оригинале (image57): тёмная «таблетка» с бегунком. */
function Switch({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="arm-switch">
      <input type="checkbox" role="switch" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="arm-switch__track" aria-hidden="true" />
      {label}
    </label>
  );
}

function Row({ row, title, isNew, open }: { row: JournalRow; title: string; isNew: boolean; open: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const at = row.registered_at ? new Date(row.registered_at) : null;
  const sms = row.channel === 'sms';
  const status = CARD_STATUS[row.display_status] ?? row.display_status;
  const victims = row.empty_call ? '' : row.has_victims ? (row.victims_count > 0 ? String(row.victims_count) : 'Есть') : 'Нет';
  return (
    <div className="arm-jitem" data-testid="journal-row">
      <div className={`arm-j112 arm-jrow${isNew ? ' arm-jrow--new' : ''}`} onDoubleClick={open} title={row.author_name ?? undefined}>
        <div><button type="button" className="arm-jbtn" aria-label={expanded ? 'Свернуть' : 'Развернуть'} aria-expanded={expanded} onClick={() => setExpanded(!expanded)}><Icon name={expanded ? 'expand_less' : 'expand_more'} size="sm" /></button></div>
        <div className="c-slate" />
        <div className={row.is_incident ? 'c-chp' : 'c-slate'} title={row.is_incident ? 'ЧП' : undefined}><Icon name="bookmark" size="sm" /></div>
        <div className={row.is_emergency ? 'c-chs' : undefined} title={row.is_emergency ? 'ЧС' : undefined}><Icon name="bolt" size="sm" /></div>
        <div><Icon name="timer" size="sm" /></div>
        <div className={sms ? (row.display_status === 'registered' ? 'c-alert' : 'c-slate') : 'c-slate'}>{sms ? 'СМС' : row.operator_number ?? ''}</div>
        <div className="c-slate">{row.arm_number ?? ''}</div>
        <div className="c-slate">{row.number}</div>
        <div className="c-slate">{at ? at.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit' }) : ''}</div>
        <div className="c-time">{at ? `${pad(at.getHours())}:${pad(at.getMinutes())}` : ''}</div>
        <div className="c-type" role="link" tabIndex={0} onClick={open} onKeyDown={(e) => e.key === 'Enter' && open()}>{title}</div>
        <div className="c-slate">{victims}</div>
        <div className={`c-status${row.display_status === 'not_notified' ? ' c-status--alert' : ''}`}>{status}</div>
        <div className="c-addr">{row.address_line ?? ''}</div>
        <div className="c-slate">{row.checked && <Icon name="check_circle" size="sm" />}</div>
      </div>
      <div className="arm-jdesc">
        <span className="arm-jdesc__label">Описание:</span>
        <span className={`arm-jdesc__text${expanded ? ' arm-jdesc__text--full' : ''}`}>{row.description ?? ''}</span>
        {expanded && row.author_name && <span className="arm-jdesc__meta">{row.author_name}</span>}
      </div>
    </div>
  );
}

export function JournalPage() {
  const me = useMe().data!;
  const navigate = useNavigate();
  const canCreate = me.permissions.includes(PERMISSIONS.trainingParticipate);
  const cardTypes = useCardTypes();
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const [applied, setApplied] = useState<Draft>(EMPTY_DRAFT);
  const [advanced, setAdvanced] = useState(false);
  const [filter, setFilter] = useState('');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [notify, setNotify] = useState(false);
  const [queue, setQueue] = useState(true);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(15);

  const picked = FILTERS.find((f) => f.value === filter)?.statuses ?? [];
  const query: JournalQuery = {
    q: applied.q.trim(),
    statuses: picked.length ? picked : queue ? [] : NOT_DRAFT,
    date_from: toIso(applied.fromDate),
    date_to: toIso(applied.toDate, true),
    page,
    page_size: pageSize,
  };
  const journal = useJournal(query, autoRefresh);
  const titles = useMemo(() => new Map((cardTypes.data ?? []).map((t) => [t.code, t.title])), [cardTypes.data]);

  // «уведомление»: новые карточки подсвечиваются, пока пользователь их не увидел
  const seen = useRef<Set<string> | null>(null);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  useEffect(() => {
    const ids = journal.data?.items.map((r) => r.id) ?? [];
    if (!journal.data) return;
    if (seen.current && notify) {
      const added = ids.filter((id) => !seen.current!.has(id));
      if (added.length) setFresh((f) => new Set([...f, ...added]));
    }
    seen.current = new Set([...(seen.current ?? []), ...ids]);
  }, [journal.data, notify]);

  const total = journal.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const first = total ? (page - 1) * pageSize + 1 : 0;
  const last = Math.min(page * pageSize, total);

  const titleOf = (r: JournalRow) => {
    if (r.empty_call) return r.empty_call === 'no_contact' ? '<Нет контакта>' : '<Срыв связи>';
    return r.card_types.map((c) => titles.get(c) ?? c).join(', ');
  };
  const open = (id: string) => { setFresh((f) => { const n = new Set(f); n.delete(id); return n; }); navigate(`/arm/112/${id}`); };
  const onSearch = (e: FormEvent) => { e.preventDefault(); setApplied(draft); setPage(1); };
  const reset = () => { setDraft(EMPTY_DRAFT); setApplied(EMPTY_DRAFT); setFilter(''); setPage(1); };

  useHotkeys({}, canCreate ? { Insert: () => navigate('/arm/112') } : {});

  // --- учебные входящие вызовы (п. 1.4): по кнопке или потоком
  const openCard = useOpenCard();
  const [ring, setRing] = useState<CallStarted | null>(null);
  const [ringError, setRingError] = useState('');
  const [stream, setStream] = useState(false);
  const ringing = useRef(false);
  const callIn = async () => {
    if (ringing.current) return;
    ringing.current = true;
    setRingError('');
    try { setRing(await startIncomingCall()); } catch (e) { setRingError((e as Error).message); ringing.current = false; }
  };
  useEffect(() => {
    if (!stream || ring) return;
    const t = setTimeout(() => { void callIn(); }, 15_000 + Math.random() * 20_000);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stream, ring]);
  const answer = () => {
    if (!ring) return;
    openCard.mutate(
      { aon: ring.aon, channel: ring.channel, scenario_id: ring.scenario_id },
      { onSuccess: (c) => navigate(`/arm/112/${c.id}?call=${ring.call_id}`) },
    );
  };
  const reject = () => {
    if (ring) void endCall(ring.call_id);
    setRing(null);
    ringing.current = false;
  };

  return (
    <div className="arm-journal" style={{ minHeight: '100vh' }}>
      <div className="arm-search">
        <form className="arm-search__main" onSubmit={onSearch}>
          <div style={{ position: 'relative' }}>
            <input className="arm-search__input" placeholder="Поиск происшествий" aria-label="Поиск происшествий"
              value={draft.q} onChange={(e) => setDraft({ ...draft, q: e.target.value })} />
            <button type="submit" className="arm-search__go" aria-label="Искать"><Icon name="search" /></button>
          </div>
          <div className="arm-search__row">
            <button type="button" className="arm-linkbtn" aria-expanded={advanced} onClick={() => setAdvanced(!advanced)}>
              расширенный по параметрам <Icon name={advanced ? 'expand_less' : 'expand_more'} size="xs" />
            </button>
            <span style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
              {canCreate && (
                <>
                  <button type="button" className="arm-newcard arm-newcard--call" onClick={() => { void callIn(); }} disabled={!!ring}>
                    <Icon name="phone" size="xs" /> учебный вызов
                  </button>
                  <button type="button" className="arm-newcard" onClick={() => navigate('/arm/112')}>создать новую карточку (insert)</button>
                </>
              )}
              <button type="button" className="arm-search__reset" onClick={reset}>сбросить</button>
            </span>
          </div>
          {advanced && (
            <div className="arm-audit__filters">
              <span>Номер, адрес, телефон, описание{me.permissions.includes(PERMISSIONS.lessonsConduct) ? ', ФИО или логин обучающегося' : ''} — в строке поиска.</span>
              <span>Дата регистрации:</span>
              <input type="date" aria-label="С даты" value={draft.fromDate} onChange={(e) => setDraft({ ...draft, fromDate: e.target.value })} />
              <span>–</span>
              <input type="date" aria-label="По дату" value={draft.toDate} onChange={(e) => setDraft({ ...draft, toDate: e.target.value })} />
              <button className="arm-audit__find" type="submit">искать</button>
            </div>
          )}
        </form>
        <ArmTopBar me={me} menu={ARM_MENU} />
      </div>

      {ring && (
        <div className="call-ring">
          <IncomingCall who={`Входящий звонок с номера ${ring.aon}`} sub="Учебный вызов · ответьте, откроется карточка" onAnswer={answer} onReject={reject} />
        </div>
      )}
      {ringError && <div className="arm112-banner" role="alert" onClick={() => setRingError('')}><b>Вызов не поступил</b><ul><li>{ringError}</li></ul></div>}
      <div className="arm-list">
        <div className="arm-list__head">
          <div className="arm-list__title">Список происшествий <Icon name="expand_less" size="sm" /></div>
          <div className="arm-list__tools">
            <span className="arm-list__notify"><Icon name="info" size="sm" /></span>
            <Switch label="уведомление" checked={notify} onChange={setNotify} />
            <Switch label="автообновление" checked={autoRefresh} onChange={setAutoRefresh} />
            <Switch label="обращения в очереди" checked={queue} onChange={(v) => { setQueue(v); setPage(1); }} />
            {canCreate && <Switch label="поток вызовов" checked={stream} onChange={setStream} />}
            <select className="arm-list__filter" aria-label="Выберите что показывать" value={filter} onChange={(e) => { setFilter(e.target.value); setPage(1); }}>
              <option value="" disabled hidden>выберите что показывать</option>
              {FILTERS.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
            </select>
          </div>
        </div>
        <div className="arm-j112 arm-jhead">
          <div /><div>Связи</div><div /><div>ЧС</div><div /><div>Опер.</div><div>АРМ</div><div>Номер</div>
          <div>Дата <Icon name="arrow_down" size="xs" /></div><div>Время</div><div>Что случилось</div>
          <div>Постр.</div><div>Статус</div><div>Адрес</div><div>Проверена</div>
        </div>
        {journal.isError && <div className="arm-empty">Не удалось загрузить журнал: {journal.error.message}</div>}
        {journal.data?.items.map((r) => <Row key={r.id} row={r} title={titleOf(r)} isNew={fresh.has(r.id)} open={() => open(r.id)} />)}
        {journal.data && total === 0 && (
          <div className="arm-empty">{applied.q || filter || applied.fromDate || applied.toDate ? 'Ничего не найдено' : 'Карточек пока нет. Новая карточка — Insert.'}</div>
        )}

        <div className="arm-pager" style={{ marginTop: 16 }}>
          <label>Страница:{' '}
            <select value={page} onChange={(e) => setPage(Number(e.target.value))}>
              {Array.from({ length: pages }, (_, i) => <option key={i + 1} value={i + 1}>{i + 1}</option>)}
            </select>
          </label>
          <label>Записей на странице:{' '}
            <select value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}>
              {PAGE_SIZES.map((n) => <option key={n}>{n}</option>)}
            </select>
          </label>
          <span>{first}-{last} из {total}</span>
          <button type="button" aria-label="Предыдущая страница" disabled={page <= 1} onClick={() => setPage(page - 1)}><Icon name="chevron_right" size="sm" style={{ transform: 'rotate(180deg)' }} /></button>
          <button type="button" aria-label="Следующая страница" disabled={page >= pages} onClick={() => setPage(page + 1)}><Icon name="chevron_right" size="sm" /></button>
        </div>
      </div>
    </div>
  );
}
