/** Реестр ДДС «Поиск происшествий / Список происшествий» (п. 2.1): вид стенда 2026 (dds/image2–5).
 *  Карточки поступают потоком, одновременно (#709): новые сверху, у каждой ожидающей — таймер от поступления
 *  до «Принята» / «Не принята» с нормативом 30 с. Уведомление — подсветка и звуковой сигнал. */
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Icon, JournalRow } from '@smena112/ui-kit';
import { useMe } from '../../shared/api/auth';
import { useCardTypes, useServices } from '../../shared/api/dictionaries';
import { SERVICE_STATUS, useDdsJournal, type DdsJournalRow } from '../../shared/api/incidents';
import { ArmTopBar, shortName } from '../../shared/ui/ArmTopBar';
import { ARM_MENU } from '../../shared/ui/armMenu';
import { rememberDds } from './DdsSelectPage';
import { PERMISSIONS } from '../../shared/api/auth';
import { feedDdsCard, useMySession } from '../../shared/api/training';
import { SessionBanner } from '../../shared/ui/SessionBanner';

export const DDS_NORM_SECONDS = 30; // ТЗ: тайминг по умолчанию; настраивается преподавателем в 4.2
const PAGE_SIZES = [10, 15, 30, 50, 100];
const WAITING = new Set(['added', 'received']);
const FILTERS: { value: string; label: string; statuses: string[] }[] = [
  { value: '', label: 'все', statuses: [] },
  { value: 'new', label: 'новые (ждут решения)', statuses: ['added', 'received'] },
  { value: 'work', label: 'в работе', statuses: ['accepted', 'response_started', 'arrived', 'works_in_progress'] },
  { value: 'done', label: 'работы завершены', statuses: ['works_completed'] },
  { value: 'refused', label: 'не приняты и отказы', statuses: ['rejected', 'works_refused'] },
];
const pad = (n: number) => String(n).padStart(2, '0');

/** Короткий сигнал о новой карточке (WebAudio — без файлов и сети). */
function beep() {
  try {
    const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    const ctx = new Ctx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.frequency.value = 880;
    gain.gain.setValueAtTime(0.15, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
    osc.connect(gain).connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.4);
  } catch { /* звук недоступен — остаётся подсветка */ }
}

export function DdsJournalPage() {
  const { service = '' } = useParams();
  const me = useMe().data!;
  const navigate = useNavigate();
  const services = useServices();
  const cardTypes = useCardTypes();
  const own = services.data?.find((s) => s.code === service);
  const [draft, setDraft] = useState('');
  const [q, setQ] = useState('');
  const [filter, setFilter] = useState('');
  const [notify, setNotify] = useState(true);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const journal = useDdsJournal(service, { q, statuses: FILTERS.find((f) => f.value === filter)?.statuses ?? [], page, page_size: pageSize }, true);
  const titles = useMemo(() => new Map((cardTypes.data ?? []).map((t) => [t.code, t.title])), [cardTypes.data]);
  useEffect(() => { rememberDds(service); }, [service]);

  // п. 4.2: на занятии с ролью ДДС этой службы карточки занятия приходят в очередь сами — темп и предел очереди
  // решает сервер (FeedDdsCard), страница только периодически спрашивает
  const session = useMySession(me.permissions.includes(PERMISSIONS.trainingParticipate)).data ?? null;
  const feeding = session?.role === 'dds' && session.dds_service_code === service && session.card_source !== 'trainee';
  const [feedNote, setFeedNote] = useState('');
  useEffect(() => {
    if (!feeding) return;
    const tick = () => feedDdsCard().then((r) => {
      setFeedNote(r.card_id ? '' : r.reason === 'очередь заполнена' ? `в очереди ${r.waiting} — новые карточки придут, когда примете решение` : '');
      if (r.card_id) void journal.refetch();
    }).catch(() => undefined);
    void tick();
    const t = setInterval(tick, 10_000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [feeding, service]);

  // таймеры ожидания тикают каждую секунду
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);

  // новые карточки: подсветка до открытия + сигнал
  const seen = useRef<Set<string> | null>(null);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  useEffect(() => {
    if (!journal.data) return;
    const ids = journal.data.items.map((r) => r.id);
    if (seen.current) {
      const added = ids.filter((id) => !seen.current!.has(id));
      if (added.length) {
        setFresh((f) => new Set([...f, ...added]));
        if (notify) beep();
      }
    }
    seen.current = new Set([...(seen.current ?? []), ...ids]);
  }, [journal.data, notify]);

  const total = journal.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const first = total ? (page - 1) * pageSize + 1 : 0;
  const last = Math.min(page * pageSize, total);
  const waitingCount = journal.data?.items.filter((r) => WAITING.has(r.service_status)).length ?? 0;
  const onSearch = (e: FormEvent) => { e.preventDefault(); setQ(draft.trim()); setPage(1); };
  const open = (id: string) => { setFresh((f) => { const n = new Set(f); n.delete(id); return n; }); navigate(`/arm/dds/${encodeURIComponent(service)}/${id}`); };

  const toInc = (r: DdsJournalRow) => {
    const reg = r.registered_at ? new Date(r.registered_at) : null;
    const saved = r.added_at ? new Date(r.added_at) : null;
    const statusAt = r.service_status_at ? new Date(r.service_status_at) : null;
    const waiting = WAITING.has(r.service_status) && saved;
    return {
      number: String(r.number),
      date: reg ? reg.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit' }) : '',
      time: reg ? `${pad(reg.getHours())}:${pad(reg.getMinutes())}:${pad(reg.getSeconds())}` : '',
      type: r.empty_call ? (r.empty_call === 'no_contact' ? '<Нет контакта>' : '<Срыв связи>') : r.card_types.map((c) => titles.get(c) ?? c).join(', '),
      victims: r.has_victims,
      address: r.address_line ?? '',
      serviceStatus: `${statusAt ? `${pad(statusAt.getHours())}:${pad(statusAt.getMinutes())} ` : ''}${SERVICE_STATUS[r.service_status] ?? r.service_status}`,
      description: r.description ?? '',
      descMeta: saved ? `${saved.toLocaleDateString('ru-RU')} ${saved.toLocaleTimeString('ru-RU')} ${r.operator_number ?? ''} ${r.author_name ? shortName(r.author_name) : ''} -` : '',
      operatorCell: r.channel === 'sms' ? 'СМС' : r.operator_number ?? '',
      arm: r.arm_number ?? '',
      waitSec: waiting ? Math.max(0, Math.floor((now - saved!.getTime()) / 1000)) : undefined,
      isNew: fresh.has(r.id),
    };
  };

  return (
    <div className="arm-journal" style={{ minHeight: '100vh' }}>
      <div className="arm-search">
        <form className="arm-search__main" onSubmit={onSearch}>
          <div style={{ position: 'relative' }}>
            <input className="arm-search__input" placeholder="Поиск происшествий" aria-label="Поиск происшествий" value={draft} onChange={(e) => setDraft(e.target.value)} />
            <button type="submit" className="arm-search__go" aria-label="Искать"><Icon name="search" /></button>
          </div>
          <div className="arm-search__row">
            <span>
              ДДС: <b>{own?.short ?? service}</b>{own && own.full !== own.short ? ` — ${own.full}` : ''}{' · '}
              <Link to="/arm/dds" className="arm-linkbtn" style={{ textDecoration: 'underline' }}>сменить службу</Link>
            </span>
            <button type="button" className="arm-search__reset" onClick={() => { setDraft(''); setQ(''); setFilter(''); setPage(1); }}>сбросить</button>
          </div>
        </form>
        <ArmTopBar me={me} menu={ARM_MENU} />
      </div>

      {session && <SessionBanner s={session} here="dds"
        extra={[session.role === 'dds' && session.dds_service_code !== service ? `ваша служба на занятии — ${session.dds_service_code}` : '',
          feeding ? `норматив решения ${session.settings.norm_dds} с` : '', feedNote].filter(Boolean).join(' · ') || undefined} />}
      <div className="arm-list">
        <div className="arm-list__head">
          <div className="arm-list__title">
            Список происшествий <Icon name="expand_less" size="sm" />
            {waitingCount > 0 && <span className="dds-waiting" role="status">ждут решения: {waitingCount}</span>}
          </div>
          <div className="arm-list__tools">
            <label className="arm-switch">
              <input type="checkbox" role="switch" checked={notify} onChange={(e) => setNotify(e.target.checked)} />
              <span className="arm-switch__track" aria-hidden="true" />
              уведомления
            </label>
            <select className="arm-list__filter" aria-label="Выберите что показать" value={filter} onChange={(e) => { setFilter(e.target.value); setPage(1); }}>
              <option value="" disabled hidden>выберите что показать</option>
              {FILTERS.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
            </select>
          </div>
        </div>
        <div className="arm-jgrid arm-jhead">
          <div /><div>Связи</div><div /><div>ЧС</div><div>Опер.</div><div>АРМ</div><div>Номер</div>
          <div>Дата <Icon name="arrow_down" size="xs" /></div><div>Время</div><div>Тип происшествия</div>
          <div>Постр.</div><div>Адрес</div><div>Статус службы</div><div>Ожидание</div><div />
        </div>
        {journal.isError && <div className="arm-empty">Не удалось загрузить реестр: {journal.error.message}</div>}
        {journal.data?.items.map((r) => <JournalRow key={r.id} inc={toInc(r)} normSec={DDS_NORM_SECONDS} onOpen={() => open(r.id)} />)}
        {journal.data && total === 0 && (
          <div className="arm-empty">{q || filter ? 'Ничего не найдено' : 'Карточек пока нет. Они появятся, когда оператор 112 направит происшествие в эту службу.'}</div>
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
