/** Раздел «Аудит» как в АРМ-112 (img/instr/image114.png): поиск события, тип, по оператору / по карточке,
 *  период; колонки Карточка, Опер., ФИО оператора, Дата, Время, Событие, Описание; 15 записей на странице. */
import { useState, type FormEvent } from 'react';
import { Icon } from '@smena112/ui-kit';
import { useMe } from '../../shared/api/auth';
import { useAudit, useEventTypes, type AuditItem, type AuditQuery } from '../../shared/api/audit';
import { ArmTopBar } from '../../shared/ui/ArmTopBar';
import { ADMIN_MENU } from '../../shared/ui/adminMenu';

const PAGE_SIZES = [15, 30, 50, 100];
const pad = (n: number) => String(n).padStart(2, '0');
const isoDate = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

interface Draft {
  q: string;
  event: string;
  byOperator: boolean;
  byCard: boolean;
  fromDate: string;
  fromTime: string;
  toDate: string;
  toTime: string;
}

/** По умолчанию — вчера 00:00 … сегодня 23:59, как в оригинале. */
function initialDraft(): Draft {
  const today = new Date();
  const yesterday = new Date(today.getTime() - 86_400_000);
  return { q: '', event: '', byOperator: true, byCard: true, fromDate: isoDate(yesterday), fromTime: '00:00', toDate: isoDate(today), toTime: '23:59' };
}

/** Локальные дата и время → ISO с часовым поясом (сервер хранит UTC). */
function toIso(date: string, time: string, endOfMinute = false): string {
  if (!date) return '';
  const d = new Date(`${date}T${time || '00:00'}:${endOfMinute ? '59.999' : '00'}`);
  return Number.isNaN(d.getTime()) ? '' : d.toISOString();
}

function toQuery(d: Draft, page: number, pageSize: number): AuditQuery {
  return {
    q: d.q.trim(),
    event: d.event,
    by_operator: d.byOperator,
    by_card: d.byCard,
    date_from: toIso(d.fromDate, d.fromTime),
    date_to: toIso(d.toDate, d.toTime, true),
    page,
    page_size: pageSize,
  };
}

function AuditRow({ item }: { item: AuditItem }) {
  const at = new Date(item.at);
  const who = item.actor_name ?? (item.actor_login ? `логин: ${item.actor_login}` : 'Система');
  return (
    <div className="arm-agrid arm-jrow" title={item.ip ? `IP ${item.ip}` : undefined}>
      <div>{item.card_number ?? '-'}</div>
      <div className="c-slate">{item.operator_number ?? ''}</div>
      <div className="c-left">{who}</div>
      <div>{at.toLocaleDateString('ru-RU')}</div>
      <div className="c-time">{pad(at.getHours())}:{pad(at.getMinutes())}<span className="t-sec">{pad(at.getSeconds())}</span></div>
      <div className="c-left">{item.event_title}</div>
      <div className="c-desc">{[item.arm_number && !item.description?.includes('АРМ') ? `АРМ ${item.arm_number}` : '', item.description].filter(Boolean).join(' · ')}</div>
    </div>
  );
}

export function AuditPage() {
  const me = useMe().data!;
  const types = useEventTypes();
  const [draft, setDraft] = useState(initialDraft);
  const [applied, setApplied] = useState(draft);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(15);
  const audit = useAudit(toQuery(applied, page, pageSize));

  const total = audit.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const first = total ? (page - 1) * pageSize + 1 : 0;
  const last = Math.min(page * pageSize, total);
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((d) => ({ ...d, [key]: value }));

  const onSearch = (e: FormEvent) => {
    e.preventDefault();
    setApplied(draft);
    setPage(1);
  };

  return (
    <div className="arm-journal" style={{ minHeight: '100vh' }}>
      <div className="arm-search">
        <form className="arm-search__main" onSubmit={onSearch}>
          <div className="arm-audit__row">
            <input className="arm-search__input" placeholder="Поиск события" aria-label="Поиск события" value={draft.q} onChange={(e) => set('q', e.target.value)} />
            <select className="arm-uline arm-uline--select" aria-label="Тип события" value={draft.event} onChange={(e) => set('event', e.target.value)} style={{ minWidth: 0 }}>
              <option value="">Тип события</option>
              {types.data?.map((t) => <option key={t.code} value={t.code}>{t.title}</option>)}
            </select>
            <button className="arm-audit__find" type="submit">искать</button>
          </div>
          <div className="arm-audit__filters">
            <span>Искать:</span>
            <label><input type="checkbox" checked={draft.byOperator} onChange={(e) => set('byOperator', e.target.checked)} /> по оператору</label>
            <label><input type="checkbox" checked={draft.byCard} onChange={(e) => set('byCard', e.target.checked)} /> по карточке</label>
          </div>
          <div className="arm-audit__filters">
            <span>Искать по датам:</span>
            <input type="date" aria-label="С даты" value={draft.fromDate} onChange={(e) => set('fromDate', e.target.value)} />
            <input type="time" aria-label="С времени" value={draft.fromTime} onChange={(e) => set('fromTime', e.target.value)} />
            <span>–</span>
            <input type="date" aria-label="По дату" value={draft.toDate} onChange={(e) => set('toDate', e.target.value)} />
            <input type="time" aria-label="По время" value={draft.toTime} onChange={(e) => set('toTime', e.target.value)} />
          </div>
        </form>
        <ArmTopBar me={me} menu={ADMIN_MENU} />
      </div>

      <div className="arm-list">
        <div className="arm-agrid arm-jhead">
          <div>Карточка</div><div>Опер.</div><div>ФИО оператора</div><div>Дата <Icon name="arrow_down" size="xs" /></div><div>Время</div><div>Событие</div><div>Описание</div>
        </div>
        {audit.isError && <div className="arm-empty">Не удалось загрузить журнал: {audit.error.message}</div>}
        {audit.data?.items.map((item) => <AuditRow key={item.id} item={item} />)}
        {audit.data && total === 0 && <div className="arm-empty">Событий за выбранный период нет</div>}

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
