/** Склейка CSS-классов: cx('a', cond && 'b') → 'a b' */
export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ');
}

/** Единый набор статусов системы. Цвет никогда не используется без иконки и подписи. */
export type Status = 'ok' | 'warn' | 'serious' | 'critical' | 'info' | 'neutral';

/** 75 → «1:15»; 5 → «0:05» */
export function formatMmSs(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

/** Таймер карточки 112: всегда две цифры минут — «02:38» */
export function formatTimer(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}

/** Статус норматива по доле израсходованного времени (порог «близко к норме» — 70%). */
export function normStatus(elapsedSec: number, normSec: number): Extract<Status, 'ok' | 'warn' | 'critical'> {
  if (elapsedSec > normSec) return 'critical';
  if (elapsedSec >= normSec * 0.7) return 'warn';
  return 'ok';
}
