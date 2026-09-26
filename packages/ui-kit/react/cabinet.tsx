/* Компоненты кабинетов (преподаватель, администратор, обучающийся). */
import type { ReactNode } from 'react';
import { Icon, type IconName } from './Icon';
import { Avatar, IconButton, StatusPill } from './primitives';
import { Sparkline } from './charts';
import { cx, type Status } from './util';

/* ======================= Каркас ======================= */
export interface NavItem { id: string; label: string; icon: IconName; href?: string; count?: number; alert?: boolean; group?: string; }

export function AppShell({ sidebar, topbar, tabbar, children }: { sidebar: ReactNode; topbar: ReactNode; tabbar?: ReactNode; children: ReactNode }) {
  return (
    <div className="cab-app">
      {sidebar}
      <div className="cab-main">
        {topbar}
        <main className="cab-content">{children}</main>
      </div>
      {tabbar}
    </div>
  );
}

export interface SidebarProps {
  role: string;
  items: NavItem[];
  activeId: string;
  user: { name: string; sub: string; initials: string };
  onNavigate?: (id: string) => void;
  onLogout?: () => void;
}
export function Sidebar({ role, items, activeId, user, onNavigate, onLogout }: SidebarProps) {
  let lastGroup: string | undefined;
  return (
    <aside className="cab-sidebar">
      <div className="cab-brand">
        <span className="cab-brand__num">112</span>
        <span><span className="cab-brand__name">СМЕНА</span><br /><span className="cab-brand__role">{role}</span></span>
      </div>
      <nav className="cab-nav" aria-label="Разделы">
        {items.map((it) => {
          const groupHeader = it.group && it.group !== lastGroup ? <div className="cab-nav__group">{it.group}</div> : null;
          lastGroup = it.group;
          const active = it.id === activeId;
          return (
            <div key={it.id}>
              {groupHeader}
              <a
                className={cx('cab-nav__item', active && 'cab-nav__item--active')}
                href={it.href ?? '#'}
                aria-current={active ? 'page' : undefined}
                onClick={(e) => { if (onNavigate) { e.preventDefault(); onNavigate(it.id); } }}
              >
                <Icon name={it.icon} />{it.label}
                {it.count != null && <span className={cx('cab-nav__count', it.alert && 'cab-nav__count--alert')}>{it.count}</span>}
              </a>
            </div>
          );
        })}
      </nav>
      <div className="cab-user">
        <Avatar initials={user.initials} />
        <span className="u-grow"><span className="cab-user__name">{user.name}</span><br /><span className="cab-user__sub">{user.sub}</span></span>
        <button type="button" onClick={onLogout} aria-label="Выйти" style={{ border: 0, background: 'none', color: 'inherit', display: 'flex' }}><Icon name="logout" size="sm" /></button>
      </div>
    </aside>
  );
}

export function TabBar({ items, activeId, onNavigate }: { items: NavItem[]; activeId: string; onNavigate?: (id: string) => void }) {
  return (
    <nav className="cab-tabbar" aria-label="Разделы">
      {items.map((it) => (
        <a key={it.id} href={it.href ?? '#'} aria-current={it.id === activeId ? 'page' : undefined}
          onClick={(e) => { if (onNavigate) { e.preventDefault(); onNavigate(it.id); } }}>
          <Icon name={it.icon} /><span>{it.label}</span>
        </a>
      ))}
    </nav>
  );
}

/** Большие часы в графитовом блоке — как на журнале АРМ. time: «11:24:26» */
export function SimClock({ label, sub, time, speed }: { label: string; sub?: string; time: string; speed?: number }) {
  return (
    <div className="cab-clock">
      <div>
        <div className="cab-clock__label">{label}</div>
        {sub && <div className="cab-clock__sub">{sub}</div>}
        {speed != null && <span className="cab-clock__speed">×{speed}</span>}
      </div>
      <div className="cab-clock__time">{time.slice(0, 5)}{time.length > 5 && <span className="t-sec">{time.slice(6, 8)}</span>}</div>
    </div>
  );
}

export function Topbar({ crumbs, title, subtitle, actions, clock }: { crumbs?: string; title: string; subtitle?: string; actions?: ReactNode; clock?: ReactNode }) {
  return (
    <header className="cab-topbar">
      <div className="cab-topbar__main">
        {crumbs && <div className="cab-crumbs">{crumbs}</div>}
        <h1 className="cab-title">{title}{subtitle && <small>{subtitle}</small>}</h1>
      </div>
      {actions && <div className="cab-topbar__actions">{actions}</div>}
      {clock}
    </header>
  );
}

/* ======================= Карточка ======================= */
export interface CardProps { title?: ReactNode; subtitle?: ReactNode; dark?: boolean; actions?: ReactNode; flush?: boolean; children: ReactNode; }
export function Card({ title, subtitle, dark, actions, flush, children }: CardProps) {
  return (
    <section className="cab-card">
      {(title || actions) && (
        <div className={cx('cab-card__head', dark && 'cab-card__head--dark')}>
          <span>
            {title && <span className="cab-card__title">{title}</span>}
            {subtitle && <><br /><span className="cab-card__sub">{subtitle}</span></>}
          </span>
          {actions}
        </div>
      )}
      <div className={cx('cab-card__body', flush && 'cab-card__body--flush')}>{children}</div>
    </section>
  );
}

/* ======================= Стат-плитка (KPI) ======================= */
export interface StatTileProps {
  label: string;
  value: ReactNode;
  unit?: string;
  /** Дельта: цвет = направление × «хорошо ли рост» */
  delta?: { text: string; direction: 'up' | 'down'; good: boolean };
  note?: ReactNode;
  trend?: number[];
  footer?: ReactNode;
}
export function StatTile({ label, value, unit, delta, note, trend, footer }: StatTileProps) {
  return (
    <div className="cab-stat">
      <span className="cab-stat__label">{label}</span>
      <span className="cab-stat__value">{value}{unit && <small>{unit}</small>}</span>
      <span className="cab-stat__foot">
        {delta && (
          <span className={cx('cab-delta', delta.good ? 'cab-delta--good' : 'cab-delta--bad')}>
            <Icon name={delta.direction === 'up' ? 'arrow_up' : 'arrow_down'} size="xs" />{delta.text}
          </span>
        )}
        {note && <span>{note}</span>}
        {footer}
        {trend && <Sparkline values={trend} />}
      </span>
    </div>
  );
}

/* ======================= Плитка обучающегося (пульт) ======================= */
export type TileState = 'ok' | 'warn' | 'critical' | 'idle' | 'offline';
const TILE_STATE: Record<TileState, { pill: Status; icon: IconName; label: string }> = {
  ok: { pill: 'ok', icon: 'check_circle', label: 'в норме' },
  warn: { pill: 'warn', icon: 'warning', label: 'близко к норме' },
  critical: { pill: 'critical', icon: 'error', label: 'сверх нормы' },
  idle: { pill: 'neutral', icon: 'timer', label: 'ждёт карточку' },
  offline: { pill: 'neutral', icon: 'close', label: 'отключён' },
};

export interface StudentTileProps {
  name: string; initials: string; role: string; state: TileState;
  cardLabel: string; cardKind: '112' | 'dds'; timer?: string; queue?: number;
  /** null — ещё нет оценок (показывается «—») */
  score: number | null; done: string; errors: number; note?: string;
  /** false — без панели действий (пока действия пульта не подключены) */
  actions?: boolean;
  onWatch?: () => void; onWhisper?: () => void; onInject?: () => void; onPause?: () => void;
}
export function StudentTile(p: StudentTileProps) {
  const st = TILE_STATE[p.state];
  const mod = p.state === 'idle' ? '' : p.state === 'offline' ? 'cab-tile--offline' : `cab-tile--${p.state}`;
  return (
    <article className={cx('cab-tile', mod)} aria-label={`${p.name}: ${st.label}`}>
      <div className="cab-tile__head">
        <Avatar initials={p.initials} light />
        <span className="u-grow"><span className="cab-tile__name">{p.name}</span><span className="cab-tile__role u-ellipsis">{p.role}</span></span>
      </div>
      <div className="cab-tile__card">
        <Icon name={p.cardKind === '112' ? 'phone' : 'clipboard'} size="sm" />
        <b className="u-ellipsis">{p.cardLabel}</b>
        {p.queue ? <span className="cab-tag cab-tag--dark">очередь {p.queue}</span> : null}
        <span className={cx('cab-tile__timer', p.state === 'critical' && 'cab-tile__timer--over')}>{p.timer ?? '—'}</span>
      </div>
      <div className="cab-tile__body">
        <span className="cab-tile__score">{p.score ?? '—'}<small>балл</small></span>
        <span className="cab-tile__meta">
          <StatusPill status={st.pill} icon={st.icon}>{st.label}</StatusPill><br />
          карточек {p.done} · ошибок {p.errors}
        </span>
      </div>
      <div className="cab-tile__note">{p.note && p.state === 'critical' && <Icon name="error" />}{p.note}</div>
      {p.actions !== false && <div className="cab-tile__actions">
        <IconButton icon="eye" label="Взгляд через плечо" onClick={p.onWatch} />
        <IconButton icon="chat" label="Шёпот-подсказка" onClick={p.onWhisper} />
        <IconButton icon="bolt" label="Вводная" onClick={p.onInject} />
        <IconButton icon="pause" label="Пауза" onClick={p.onPause} />
      </div>}
    </article>
  );
}

/* ======================= Лента событий ======================= */
export interface FeedItem { id: string; time: string; status: Status; who: string; text: string; sub?: string; }
const FEED_ICON: Record<Status, IconName> = { ok: 'check_circle', warn: 'warning', serious: 'warning', critical: 'error', info: 'info', neutral: 'close' };
export function EventFeed({ items }: { items: FeedItem[] }) {
  return (
    <ul className="cab-feed" aria-live="polite">
      {items.map((f) => (
        <li key={f.id} className="cab-feed__item">
          <span className="cab-feed__time">{f.time}</span>
          <span className={cx('cab-feed__icon', `cab-feed__icon--${f.status === 'serious' ? 'warn' : f.status}`)}><Icon name={FEED_ICON[f.status]} /></span>
          <span><span className="cab-feed__who">{f.who}</span>: {f.text}{f.sub && <span className="cab-feed__sub">{f.sub}</span>}</span>
        </li>
      ))}
    </ul>
  );
}

/* ======================= Плитка сервиса (админ) ======================= */
export type ServiceState = 'ok' | 'warn' | 'critical' | 'off';
const SVC_PILL: Record<ServiceState, { status: Status; icon: IconName; label: string }> = {
  ok: { status: 'ok', icon: 'check_circle', label: 'работает' },
  warn: { status: 'warn', icon: 'warning', label: 'деградация' },
  critical: { status: 'critical', icon: 'error', label: 'недоступен' },
  off: { status: 'neutral', icon: 'close', label: 'выключен' },
};
export interface ServiceHealthProps { name: string; icon: IconName; state: ServiceState; metrics: [string, string][]; actions?: ReactNode; }
export function ServiceHealth({ name, icon, state, metrics, actions }: ServiceHealthProps) {
  const p = SVC_PILL[state];
  return (
    <article className={cx('cab-svc', state !== 'ok' && `cab-svc--${state}`)}>
      <div className="cab-svc__head">
        <span className="cab-svc__name"><Icon name={icon} size="sm" />{name}</span>
        <StatusPill status={p.status} icon={p.icon}>{p.label}</StatusPill>
      </div>
      <div className="cab-svc__metrics">
        {metrics.map(([k, v]) => <div key={k} className="cab-svc__metric"><span>{k}</span><b>{v}</b></div>)}
      </div>
      {actions && <div className="u-row">{actions}</div>}
    </article>
  );
}
