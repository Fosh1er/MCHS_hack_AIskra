/** Модуль training: учебные звонки (п. 1.4, 2.3), банк сценариев (п. 3.2, 4.1) и занятия (п. 4.2). */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { http } from './http';

export interface CallStarted { call_id: string; scenario_id: string | null; aon: string; channel: string }
export interface Replica { speaker: 'party' | 'operator' | 'system'; text: string }
export interface CallMessage { speaker: 'party' | 'operator' | 'system'; text: string; at: string }
export interface CallView {
  id: string; role: string; party: 'applicant' | 'brigade' | 'service'; direction: 'in' | 'out'; status: string; aon: string;
  card_id: string | null; service_code: string | null; target_service: string | null;
  started_at: string; answered_at: string | null; ended_at: string | null; messages: CallMessage[];
}

const T = '/api/v1/training';
const post = <R,>(path: string, body: unknown = {}) => http<R>(`${T}${path}`, { method: 'POST', body: JSON.stringify(body) });

export const startIncomingCall = (b: { groups?: number[]; difficulty?: number } = {}) => post<CallStarted>('/calls/incoming', b);
export const answerCall = (id: string, cardId: string | null) => post<Replica | null>(`/calls/${id}/answer`, { card_id: cardId });
export const sendReplica = (id: string, text: string) => post<Replica>(`/calls/${id}/replicas`, { text });
export const endCall = (id: string) => post<{ status: string }>(`/calls/${id}/end`);
export const startDdsCall = (b: { card_id: string; service_code: string; party: CallView['party']; target_service?: string | null; incoming?: boolean }) =>
  post<CallStarted>('/calls/dds', b);
export const getCall = (id: string) => http<CallView>(`${T}/calls/${id}`);

export const useCardCalls = (cardId: string | undefined) =>
  useQuery({ queryKey: ['card-calls', cardId], queryFn: () => http<CallView[]>(`${T}/cards/${cardId}/calls`), enabled: !!cardId });

// ------------------------------------------------------------------ п. 4.1: банк сценариев
export interface ScenarioRow {
  id: string; title: string; status: 'draft' | 'approved' | 'archived'; difficulty: number;
  card_type_code: string | null; incident_type_code: string | null; source: string; created_at: string | null;
}
export interface ScenarioView {
  id: string; title: string; status: ScenarioRow['status']; difficulty: number; source: string;
  card_type_code: string; incident_type_code: string;
  legend: Record<string, unknown> & { opening?: string; what?: string; details?: string; facts?: Record<string, string>; persona?: Record<string, unknown> };
  reference_card: Record<string, unknown> & { final_type?: string; services?: { code: string; main: boolean }[] };
  reference_dds: Record<string, unknown>;
}
export interface PreviewItem { question: string; answer: string; reference: string }
export interface ScenarioFilter { status?: string; difficulty?: number; card_type?: string; source?: string; page: number; page_size: number }

const qs = (o: Record<string, unknown>) =>
  new URLSearchParams(Object.entries(o).filter(([, v]) => v !== undefined && v !== '' && v !== null).map(([k, v]) => [k, String(v)]));

export const useScenarios = (f: ScenarioFilter) =>
  useQuery({ queryKey: ['scenarios', f], queryFn: () => http<{ items: ScenarioRow[]; total: number }>(`${T}/scenarios?${qs({ ...f })}`), placeholderData: keepPreviousData });
export const useScenario = (id: string | null) =>
  useQuery({ queryKey: ['scenario', id], queryFn: () => http<ScenarioView>(`${T}/scenarios/${id}`), enabled: !!id });
export const useScenarioPreview = (id: string | null, enabled: boolean) =>
  useQuery({ queryKey: ['scenario-preview', id], queryFn: () => http<PreviewItem[]>(`${T}/scenarios/${id}/preview`), enabled: !!id && enabled });

function useInvalidating<V, R>(fn: (v: V) => Promise<R>, keys: string[][]) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => keys.forEach((k) => qc.invalidateQueries({ queryKey: k })) });
}
export const useGenerateScenarios = () =>
  useInvalidating((b: { count: number; groups: number[]; difficulty: number }) => post<{ ids: string[] }>('/scenarios/generate', b), [['scenarios']]);
export const useReviewScenario = () =>
  useInvalidating(({ id, approve }: { id: string; approve: boolean }) => post<{ status: string }>(`/scenarios/${id}/${approve ? 'approve' : 'archive'}`), [['scenarios'], ['scenario']]);
export interface ScenarioEdit { title?: string; difficulty?: number; opening?: string; what?: string; details?: string; comment?: string }
export const useEditScenario = () =>
  useInvalidating(({ id, ...b }: ScenarioEdit & { id: string }) => http<{ status: string }>(`${T}/scenarios/${id}`, { method: 'PATCH', body: JSON.stringify(b) }),
    [['scenarios'], ['scenario'], ['scenario-preview']]);

// ------------------------------------------------------------------ п. 4.2: занятия
export type SessionMode = 'cards_112' | 'dds_actions' | 'mixed';
export type CardSource = 'generated' | 'trainee' | 'mixed';
export interface SessionSettings {
  norm_112: number; norm_dds: number; threshold: number; difficulty: number;
  call_interval_s: number; feed_interval_s: number; max_waiting: number;
}
export interface Participant { student_id: string; full_name: string; login: string; role: '112' | 'dds'; dds_service_code: string | null }
export interface SessionView {
  id: string; title: string; mode: SessionMode; card_source: CardSource; status: 'planned' | 'running' | 'finished';
  groups: number[]; settings: SessionSettings; started_at: string | null; finished_at: string | null; participants: Participant[];
}
export interface StudentRow { id: string; login: string; full_name: string; operator_number: string | null }
export interface ParticipantProgress {
  student_id: string; cards_done: number; current_card: number | null; current_label: string; current_since: string | null;
  waiting: number; avg_score: number | null; errors: number; last_errors: string[];
}
export interface MonitorView { session: SessionView; rows: { participant: Participant; progress: ParticipantProgress }[] }
export interface MySession {
  session_id: string; title: string; mode: SessionMode; card_source: CardSource; role: '112' | 'dds';
  dds_service_code: string | null; groups: number[]; settings: SessionSettings; started_at: string | null;
}
export interface CreateSessionBody {
  title: string; mode: SessionMode; card_source: CardSource; groups: number[];
  participants: { student_id: string; role: '112' | 'dds'; dds_service_code?: string | null }[];
  settings: SessionSettings;
}

export const MODE_TITLE: Record<SessionMode, string> = { cards_112: 'Карточки 112', dds_actions: 'Действия ДДС', mixed: 'Смешанное: 112 и ДДС' };
export const SOURCE_TITLE: Record<CardSource, string> = { generated: 'сгенерированные системой', trainee: 'от операторов 112 занятия', mixed: 'смешанный' };
export const SESSION_STATUS: Record<SessionView['status'], string> = { planned: 'запланировано', running: 'идёт', finished: 'завершено' };

export const useStudents = () => useQuery({ queryKey: ['students'], queryFn: () => http<StudentRow[]>(`${T}/students`) });
export const useSessions = () =>
  useQuery({ queryKey: ['sessions'], queryFn: () => http<{ items: SessionView[]; total: number }>(`${T}/sessions?page_size=100`) });
export const useMonitor = (id: string) =>
  useQuery({ queryKey: ['monitor', id], queryFn: () => http<MonitorView>(`${T}/sessions/${id}/monitor`), refetchInterval: 5_000 });
export const useCreateSession = () => useInvalidating((b: CreateSessionBody) => post<{ id: string }>('/sessions', b), [['sessions']]);
export const useSessionState = (id: string) =>
  useInvalidating((start: boolean) => post<{ status: string }>(`/sessions/${id}/${start ? 'start' : 'finish'}`), [['sessions'], ['monitor', id]]);
/** Идущее занятие обучающегося: опрашивается, чтобы старт и завершение преподавателем подхватывались без перезагрузки. */
export const useMySession = (enabled = true) =>
  useQuery({ queryKey: ['my-session'], queryFn: () => http<MySession | null>(`${T}/sessions/my`), enabled, refetchInterval: 10_000 });
export const feedDdsCard = () => post<{ card_id: string | null; waiting: number; reason: string }>('/sessions/feed');
