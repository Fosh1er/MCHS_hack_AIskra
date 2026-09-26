import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { Icon, type IconName } from './Icon';
import { cx, type Status } from './util';

/* ---------- Button ---------- */
export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'default' | 'primary' | 'dark' | 'danger' | 'ghost';
  size?: 'md' | 'sm';
  icon?: IconName;
}
export function Button({ variant = 'default', size = 'md', icon, className, children, type = 'button', ...rest }: ButtonProps) {
  return (
    <button
      type={type}
      className={cx('cab-btn', variant !== 'default' && `cab-btn--${variant}`, size === 'sm' && 'cab-btn--sm', className)}
      {...rest}
    >
      {icon && <Icon name={icon} size="sm" />}
      {children}
    </button>
  );
}

/* ---------- IconButton ---------- */
export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon: IconName;
  /** Обязательная подпись для доступности (aria-label + всплывающая подсказка). */
  label: string;
}
export function IconButton({ icon, label, className, type = 'button', ...rest }: IconButtonProps) {
  return (
    <button type={type} className={cx('cab-iconbtn', className)} aria-label={label} title={label} {...rest}>
      <Icon name={icon} />
    </button>
  );
}

/* ---------- Segmented (фильтр-сегменты) ---------- */
export interface SegmentedOption<T extends string> { value: T; label: ReactNode; }
export interface SegmentedProps<T extends string> {
  options: SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  ariaLabel: string;
}
export function Segmented<T extends string>({ options, value, onChange, ariaLabel }: SegmentedProps<T>) {
  return (
    <div className="cab-seg" role="group" aria-label={ariaLabel}>
      {options.map((o) => (
        <button key={o.value} type="button" aria-pressed={o.value === value} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

/* ---------- StatusPill: иконка статусного цвета + подпись ---------- */
const STATUS_ICON: Record<Status, IconName> = {
  ok: 'check_circle', warn: 'warning', serious: 'warning', critical: 'error', info: 'info', neutral: 'close',
};
export interface StatusPillProps {
  status: Status;
  children: ReactNode;
  /** light — кабинеты (.cab-pill), dark — АРМ и тёмные панели (.arm-pill) */
  surface?: 'light' | 'dark';
  icon?: IconName;
}
export function StatusPill({ status, children, surface = 'light', icon }: StatusPillProps) {
  const base = surface === 'dark' ? 'arm-pill' : 'cab-pill';
  return (
    <span className={cx(base, `${base}--${status}`)}>
      <Icon name={icon ?? STATUS_ICON[status]} />
      {children}
    </span>
  );
}

/* ---------- Tag ---------- */
export function Tag({ variant = 'default', children }: { variant?: 'default' | 'dark' | 'blue'; children: ReactNode }) {
  return <span className={cx('cab-tag', variant !== 'default' && `cab-tag--${variant}`)}>{children}</span>;
}

/* ---------- Avatar ---------- */
export function Avatar({ initials, light = false }: { initials: string; light?: boolean }) {
  return <span className={cx('cab-avatar', light && 'cab-avatar--light')} aria-hidden="true">{initials}</span>;
}

/* ---------- Banner ---------- */
export interface BannerProps { status?: 'warn' | 'critical'; children: ReactNode; actions?: ReactNode; }
export function Banner({ status = 'warn', children, actions }: BannerProps) {
  return (
    <div className={cx('cab-banner', status === 'critical' && 'cab-banner--critical')} role="status">
      <Icon name={status === 'critical' ? 'error' : 'warning'} />
      <span>{children}</span>
      {actions && <span className="cab-banner__actions">{actions}</span>}
    </div>
  );
}

/* ---------- Meter: трек — светлый шаг того же тона, заливка несёт серьёзность ---------- */
export interface MeterProps {
  label: string;
  /** 0..1 */
  value: number;
  display: ReactNode;
  status?: 'ok' | 'warn' | 'critical';
}
export function Meter({ label, value, display, status = 'ok' }: MeterProps) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <div className={cx('cab-meter', status !== 'ok' && `cab-meter--${status}`)}>
      <span className="cab-meter__label">{label}</span>
      <span className="cab-meter__track" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} aria-label={label}>
        <span className="cab-meter__fill" style={{ display: 'block', width: `${pct}%` }} />
      </span>
      <span className="cab-meter__value">{display}</span>
    </div>
  );
}
