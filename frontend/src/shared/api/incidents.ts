/** Модуль incidents: карточка происшествия 112 (п. 1.1), журнал и работа с сохранённой карточкой (п. 1.3). */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, http } from './http';
import { WRITE_RETRY } from './resilience';

export interface CardAddress {
  raw: string; country: string; region: string; city: string; object: string; okrug: string | null; district: string | null;
  street: string; house: string; building: string; structure: string; flat: string; entrance: string; floor: string;
  code: string; descriptive: string; lat: number | null; lon: number | null;
}
export interface CardData {
  phones: { aon: string; provided: string; on_site: string; foreign: boolean };
  channel: string | null;
  applicant: { name: string; status: string | null; foreign_language: boolean };
  victims: { has: boolean; count: number };
  card_types: string[];
  incident_types: string[];
  questionnaire: Record<string, Record<string, string>>;
  card_flags: string[];
  address: CardAddress;
  description: string;
  services?: string[];
  flags: { no_contact: boolean; call_dropped: boolean; refusal_103: boolean; emergency: boolean; incident: boolean };
}
export interface CardServiceIn { code: string; is_main: boolean; added_by: 'auto' | 'manual'; service_type?: string | null }
export interface CardOpened { id: string; number: number; opened_at: string }
export interface CardSaved { id: string; number: number; status: string; saved_at: string; processing_ms: number; services: CardServiceIn[] }
export interface StatusHistoryItem { status: string; at: string | null; operator: string | null; comment: string | null; order_no?: string | null }
export interface CardServiceView {
  code: string; short: string; integrated: boolean; is_main: boolean; added_by: string;
  status: string; status_at: string | null; history: StatusHistoryItem[];
}
export interface WorkoutView {
  id: string; at: string; operator_number: string | null; service_code: string | null;
  target: string; called_to: string; phone: string; receiver: string; message: string;
}
export interface IncidentTypeInfo { code: string; final_type: string | null; ekp_type: string | null }
export interface CardView {
  id: string; number: number; status: string; display_status: string; author_id: string | null; author_name: string | null;
  operator_number: string | null; arm_number: string | null; opened_at: string | null; saved_at: string | null;
  worked_at: string | null; checked_at: string | null; checked_by_name: string | null;
  rework: { comment: string; at: string | null; by: string | null } | null;
  processing_ms: number | null; is_emergency: boolean; is_incident: boolean; address_line: string | null;
  data: Partial<CardData>; services: CardServiceView[]; workouts: WorkoutView[]; incident_types: IncidentTypeInfo[];
}

const I = '/api/v1/incidents/cards';

export const useOpenCard = () =>
  useMutation({ mutationFn: (body: { aon?: string; channel?: string | null; scenario_id?: string | null; session_id?: string | null }) => http<CardOpened>(I, { method: 'POST', body: JSON.stringify(body) }) });

/** Сохранение переживает обрыв связи (6.1): повтор при сетевой ошибке. Если сервер успел сохранить, а ответ
 *  потерялся, повтор получит «уже сохранена» — это тоже успех. */
export const useSaveCard = (id: string) =>
  useMutation<CardSaved | null, Error, { data: CardData; services: CardServiceIn[] }>({
    mutationFn: async (body: { data: CardData; services: CardServiceIn[] }) => {
      try {
        return await http<CardSaved>(`${I}/${id}/save`, { method: 'POST', body: JSON.stringify(body) });
      } catch (e) {
        if (e instanceof ApiError && e.code === 'card_already_saved') return null;
        throw e;
      }
    },
    ...WRITE_RETRY,
  });

export const useCard = (id: string | undefined) =>
  useQuery({ queryKey: ['card', id], queryFn: () => http<CardView>(`${I}/${id}`), enabled: !!id });

// ------------------------------------------------------------------ п. 1.3: журнал и сохранённая карточка

/** Строка «Списка происшествий» (image57, image113). */
export interface JournalRow {
  id: string; number: number; display_status: string; checked: boolean; is_emergency: boolean; is_incident: boolean;
  operator_number: string | null; arm_number: string | null; author_name: string | null; channel: string | null;
  registered_at: string | null; card_types: string[]; empty_call: 'no_contact' | 'call_dropped' | null;
  has_victims: boolean; victims_count: number; address_line: string | null; description: string | null;
}
export interface JournalPage { items: JournalRow[]; total: number; page: number; page_size: number }
export interface JournalQuery {
  q: string; statuses: string[]; date_from: string; date_to: string; page: number; page_size: number;
}

/** Статусы журнала: коды сервера → подписи оригинала. */
export const CARD_STATUS: Record<string, string> = {
  draft: 'Заполняется', registered: 'Зарегистрирована', not_notified: 'Не оповещено', worked: 'Отработана',
  checked: 'Проверена', completed: 'Завершена', not_completed: 'Не завершено', refusal: 'Отказ',
};
export const SERVICE_STATUS: Record<string, string> = {
  added: 'Добавлена', received: 'Получена службой', accepted: 'Принята', rejected: 'Не принята',
  response_started: 'Начало реагирования', arrived: 'Прибытие', works_in_progress: 'Проведение работ',
  works_completed: 'Работы завершены', works_refused: 'Отказ от выполнения работ',
};

const journalParams = (q: JournalQuery) => {
  const p = new URLSearchParams({ page: String(q.page), page_size: String(q.page_size) });
  if (q.q) p.set('q', q.q);
  q.statuses.forEach((st) => p.append('status', st));
  if (q.date_from) p.set('date_from', q.date_from);
  if (q.date_to) p.set('date_to', q.date_to);
  return p.toString();
};

/** Журнал; автообновление — опрос раз в 5 с (push через WebSocket — в 2.x, ADR-0005). */
export const useJournal = (q: JournalQuery, autoRefresh: boolean) =>
  useQuery({
    queryKey: ['journal', q],
    queryFn: () => http<JournalPage>(`/api/v1/incidents/journal?${journalParams(q)}`),
    placeholderData: keepPreviousData,
    refetchInterval: autoRefresh ? 5000 : false,
    refetchIntervalInBackground: true, // окно АРМ часто в фоне — новые карточки и сигнал всё равно приходят
  });

export interface AppendBody { fields: Record<string, string>; description_add: string; victims_count: number | null }
export interface WorkoutBody {
  service_code: string | null; target: string; called_to: string; phone: string; receiver: string; message: string;
}

/** Действия с сохранённой карточкой; после успеха обновляются карточка и журнал. */
export function useCardActions(id: string) {
  const qc = useQueryClient();
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['card', id] });
    qc.invalidateQueries({ queryKey: ['journal'] });
  };
  const post = <T,>(path: string) => (body: unknown) =>
    http<T>(`${I}/${id}/${path}`, { method: 'POST', body: JSON.stringify(body) });
  const opts = { onSuccess: refresh };
  return {
    worked: useMutation({ mutationFn: (comment: string) => post<{ status: string }>('worked')({ comment }), ...opts }),
    checked: useMutation({ mutationFn: (comment: string) => post<{ status: string }>('checked')({ comment }), ...opts }),
    returned: useMutation({ mutationFn: (comment: string) => post<{ status: string }>('returned')({ comment }), ...opts }),
    flags: useMutation({ mutationFn: post<{ changed: string[] }>('flags') as (b: { emergency: boolean; incident: boolean }) => Promise<{ changed: string[] }>, ...opts }),
    append: useMutation({ mutationFn: post<{ changed: string[] }>('append') as (b: AppendBody) => Promise<{ changed: string[] }>, ...opts }),
    workout: useMutation({ mutationFn: post<{ id: string }>('workouts') as (b: WorkoutBody) => Promise<{ id: string }>, ...opts }),
  };
}

/** «Просмотр карточки» в аудите — один раз при открытии (а не при каждом обновлении экрана). */
export const markCardViewed = (id: string) => http<void>(`${I}/${id}/viewed`, { method: 'POST' });

// ------------------------------------------------------------------ п. 2.1, 2.2: АРМ ДДС

/** Строка реестра ДДС (dds/image3–5). */
export interface DdsJournalRow {
  id: string; number: number; is_emergency: boolean; is_incident: boolean; operator_number: string | null;
  arm_number: string | null; channel: string | null; registered_at: string | null; card_types: string[];
  empty_call: 'no_contact' | 'call_dropped' | null; has_victims: boolean; victims_count: number;
  address_line: string | null; description: string | null; author_name: string | null;
  service_status: string; service_status_at: string | null; added_at: string | null;
}
export interface DdsJournalPage { items: DdsJournalRow[]; total: number; page: number; page_size: number }
export interface DdsCardView { card: CardView; service_code: string; service_status: string; next_statuses: string[] }
export interface ServiceStatusBody { status: string; order_no: string; comment: string }

const DDS = '/api/v1/incidents/dds';

export const useDdsJournal = (service: string, q: { q: string; statuses: string[]; page: number; page_size: number }, autoRefresh: boolean) =>
  useQuery({
    queryKey: ['dds-journal', service, q],
    queryFn: () => {
      const p = new URLSearchParams({ page: String(q.page), page_size: String(q.page_size) });
      if (q.q) p.set('q', q.q);
      q.statuses.forEach((s) => p.append('status', s));
      return http<DdsJournalPage>(`${DDS}/${encodeURIComponent(service)}/journal?${p}`);
    },
    placeholderData: keepPreviousData,
    refetchInterval: autoRefresh ? 5000 : false,
    refetchIntervalInBackground: true, // окно АРМ часто в фоне — новые карточки и сигнал всё равно приходят
  });

export const useDdsCard = (service: string, id: string | undefined) =>
  useQuery({
    queryKey: ['dds-card', service, id],
    queryFn: () => http<DdsCardView>(`${DDS}/${encodeURIComponent(service)}/cards/${id}`),
    enabled: !!id,
    refetchInterval: 5000, // статусы других служб меняются, пока карточка открыта
  });

export function useDdsActions(service: string, id: string) {
  const qc = useQueryClient();
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['dds-card', service, id] });
    qc.invalidateQueries({ queryKey: ['dds-journal', service] });
  };
  const base = `${DDS}/${encodeURIComponent(service)}/cards/${id}`;
  return {
    received: useMutation({ mutationFn: () => http<{ status: string }>(`${base}/received`, { method: 'POST' }), onSuccess: refresh }),
    status: useMutation({
      mutationFn: (b: ServiceStatusBody) => http<{ status: string }>(`${base}/status`, { method: 'POST', body: JSON.stringify(b) }),
      onSuccess: refresh,
    }),
  };
}
