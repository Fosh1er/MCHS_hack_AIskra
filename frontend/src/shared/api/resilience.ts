/** Устойчивость к сбоям связи (п. 6.1, ТЗ: сбой до 30 с без потери работы).
 *  - сетевая ошибка или 502/503/504 (сервер перезапускается, прокси не достучался) — повторяем;
 *  - ошибки бизнес-правил (4xx) — не повторяем: их нужно показать пользователю;
 *  - черновик карточки 112 хранится в localStorage до успешного сохранения. */
import { ApiError } from './http';

/** 5xx без нашего JSON (`http_error`) — ответ прокси, а не приложения: nginx 502, дев-прокси Vite 500. */
export const isTransient = (e: unknown) =>
  !(e instanceof ApiError) || [0, 502, 503, 504].includes(e.status) || (e.status >= 500 && e.code === 'http_error');

/** Повтор записи: каждые 3 с в течение минуты — с запасом покрывает сбой до 30 с. */
export const WRITE_RETRY = {
  retry: (count: number, e: Error) => isTransient(e) && count < 20,
  retryDelay: 3_000,
} as const;

const KEY = (id: string) => `aiskra:draft:${id}`;
const VERSION = 1;

export function loadDraft<T>(id: string): { state: T; at: number } | null {
  try {
    const raw = localStorage.getItem(KEY(id));
    if (!raw) return null;
    const d = JSON.parse(raw) as { v: number; state: T; at: number };
    return d.v === VERSION ? { state: d.state, at: d.at } : null;
  } catch {
    return null;
  }
}

export function saveDraft<T>(id: string, state: T): void {
  try { localStorage.setItem(KEY(id), JSON.stringify({ v: VERSION, state, at: Date.now() })); } catch { /* квота или приватный режим */ }
}

export function dropDraft(id: string): void {
  try { localStorage.removeItem(KEY(id)); } catch { /* нет хранилища */ }
}
