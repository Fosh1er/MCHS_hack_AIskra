/** Тонкая обёртка над fetch. Ошибки бэкенда приходят как {error, message} (aiskra.main).
 *  Сессия — HttpOnly-cookie (ADR-0010): браузер отправляет её сам, код её не видит. */
export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

export async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.error ?? 'http_error', body.message ?? res.statusText);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export const isUnauthorized = (e: unknown) => e instanceof ApiError && e.status === 401;
