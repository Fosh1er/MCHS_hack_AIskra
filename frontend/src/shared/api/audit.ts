/** Модуль audit: поиск по журналу (только администратор). */
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { http } from './http';

export interface AuditItem {
  id: number;
  at: string;
  card_number: number | null;
  operator_number: string | null;
  actor_name: string | null;
  actor_login: string | null;
  actor_role: string | null;
  arm_number: string | null;
  event: string;
  event_title: string;
  description: string | null;
  ip: string | null;
}
export interface AuditPage { items: AuditItem[]; total: number; page: number; page_size: number }
export interface EventType { code: string; title: string }

export interface AuditQuery {
  q: string;
  by_operator: boolean;
  by_card: boolean;
  event: string;
  date_from: string; // ISO
  date_to: string;
  page: number;
  page_size: number;
}

function toParams(q: AuditQuery): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) if (v !== '' && v !== undefined) p.set(k, String(v));
  return p.toString();
}

export const useAudit = (q: AuditQuery) =>
  useQuery({
    queryKey: ['audit', q],
    queryFn: () => http<AuditPage>(`/api/v1/audit?${toParams(q)}`),
    placeholderData: keepPreviousData,
  });

export const useEventTypes = () =>
  useQuery({ queryKey: ['audit', 'event-types'], queryFn: () => http<EventType[]>('/api/v1/audit/event-types'), staleTime: Infinity });
