/** Модуль training: учебные звонки (п. 1.4, 2.3), банк сценариев (п. 3.2, 4.1) и занятия (п. 4.2). */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, http } from './http';

export interface CallStarted { call_id: string; scenario_id: string | null; aon: string; channel: string }
/** Что изменило состояние заявителя: код правила и сработавший фрагмент реплики оператора (п. 3.6). */
export interface ToneChange { reason: 'calming' | 'invalidating' | 'pressure' | 'on_topic'; fragment: string; tension: number; trust: number; readiness: number }
/** Состояние ИИ-заявителя у его реплики (п. 3.6): шкалы 0–10 и подача голоса. Фактов легенды здесь нет. */
export interface Tone {
  emotion: string; emotion_title: string; tension: number; trust: number; readiness: number; band: 'calm' | 'tense' | 'panic';
  pace: 'slow' | 'normal' | 'fast' | 'very_fast'; volume: 'whisper' | 'low' | 'normal' | 'loud'; breathing: string; changes: ToneChange[];
}
export interface Replica { speaker: 'party' | 'operator' | 'system'; text: string; message_id?: string | null; tone?: Tone | null }
export interface CallMessage { speaker: 'party' | 'operator' | 'system'; text: string; at: string; id?: string | null; tone?: Tone | null }
export interface CallView {
  id: string; role: string; party: 'applicant' | 'brigade' | 'service'; direction: 'in' | 'out'; status: string; aon: string;
  card_id: string | null; service_code: string | null; target_service: string | null;
  started_at: string; answered_at: string | null; ended_at: string | null; messages: CallMessage[]; tone?: Tone | null;
  mode?: ReplicaVia; // как оператор вёл разговор: самый «голосовой» из способов его реплик
}

const T = '/api/v1/training';
const post = <R,>(path: string, body: unknown = {}) => http<R>(`${T}${path}`, { method: 'POST', body: JSON.stringify(body) });

export const startIncomingCall = (b: { groups?: number[]; difficulty?: number } = {}) => post<CallStarted>('/calls/incoming', b);
export const answerCall = (id: string, cardId: string | null) => post<Replica | null>(`/calls/${id}/answer`, { card_id: cardId });
/** Как оператор сказал реплику (п. 3.6): напечатал, кнопкой «говорить» или без рук — режим звонка видит отчёт. */
export type ReplicaVia = 'text' | 'voice' | 'hands_free';
export const sendReplica = (id: string, text: string, via: ReplicaVia = 'text') => post<Replica>(`/calls/${id}/replicas`, { text, via });
export const endCall = (id: string) => post<{ status: string }>(`/calls/${id}/end`);
export const startDdsCall = (b: { card_id: string; service_code: string; party: CallView['party']; target_service?: string | null; incoming?: boolean }) =>
  post<CallStarted>('/calls/dds', b);
export const getCall = (id: string) => http<CallView>(`${T}/calls/${id}`);

// ------------------------------------------------------------------ речь: голосовой ввод (п. 1.4) и голос собеседника (п. 3.6)
/** `enabled` — распознавание (кнопка «говорить»); `tts` — серверный синтез, иначе озвучивает браузер. */
export const useSpeechStatus = () =>
  useQuery({ queryKey: ['speech-status'], queryFn: () => http<{ enabled: boolean; tts: boolean }>(`${T}/speech`), staleTime: 60_000 });
/** Звук реплики собеседника — адрес своего сайта: CSP стенда не пускает `blob:` в медиа (п. 3.6). */
export const replicaAudioUrl = (callId: string, messageId: string) => `${T}/calls/${callId}/messages/${messageId}/audio`;
export async function transcribe(audio: Blob): Promise<string> {
  const body = new FormData();
  body.append('audio', audio, audio.type.includes('wav') ? 'speech.wav' : audio.type.includes('ogg') ? 'speech.ogg' : 'speech.webm');
  const res = await fetch(`${T}/speech`, { method: 'POST', body, credentials: 'same-origin' });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, data.error ?? 'http_error', data.message ?? res.statusText);
  return String(data.text ?? '');
}

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
  caller_emotion?: string; caller_tension?: number | null; // заявитель в идущем звонке (п. 3.6)
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
  useQuery({ queryKey: ['monitor', id], queryFn: () => http<MonitorView>(`${T}/sessions/${id}/monitor`), refetchInterval: 5_000, staleTime: 0 });
export const useCreateSession = () => useInvalidating((b: CreateSessionBody) => post<{ id: string }>('/sessions', b), [['sessions']]);
export const useSessionState = (id: string) =>
  useInvalidating((start: boolean) => post<{ status: string }>(`/sessions/${id}/${start ? 'start' : 'finish'}`), [['sessions'], ['monitor', id]]);
/** Идущее занятие обучающегося: опрашивается, чтобы старт и завершение преподавателем подхватывались без перезагрузки. */
export const useMySession = (enabled = true) =>
  useQuery({ queryKey: ['my-session'], queryFn: () => http<MySession | null>(`${T}/sessions/my`), enabled, refetchInterval: 10_000 });
export const feedDdsCard = () => post<{ card_id: string | null; waiting: number; reason: string }>('/sessions/feed');

export interface MySessionRow {
  session_id: string; title: string; mode: SessionMode; status: SessionView['status']; role: '112' | 'dds';
  dds_service_code: string | null; started_at: string | null; finished_at: string | null; settings: SessionSettings;
}
export const useMySessions = () =>
  useQuery({ queryKey: ['my-sessions'], queryFn: () => http<MySessionRow[]>(`${T}/sessions/mine`), refetchInterval: 15_000 });
export const useSessionDefaults = () =>
  useQuery({ queryKey: ['session-defaults'], queryFn: () => http<SessionSettings>(`${T}/session-defaults`) });
/** Куда вести обучающегося в занятии: журнал 112 или АРМ своей ДДС. */
export const armFor = (s: { role: '112' | 'dds'; dds_service_code: string | null }) =>
  s.role === 'dds' && s.dds_service_code ? `/arm/dds/${encodeURIComponent(s.dds_service_code)}` : '/arm/112/journal';
