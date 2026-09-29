/** Модуль training: учебные звонки (п. 1.4, 2.3), банк сценариев (п. 3.2, 4.1) и занятия (п. 4.2). */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, http } from './http';

export interface CallStarted { call_id: string; scenario_id: string | null; aon: string; channel: string; warning?: string | null }
/** Параметры голоса реплики (п. 3.6): контракт для синтеза речи и дуплекс-адаптера — модуль голоса делается отдельно. */
export interface VoiceParams {
  profile: string; direction: 'up' | 'down'; level: number; rate: number; pitch_st: number; gain_db: number;
  nonverbal: string[]; scene: string | null; voice: 'child' | 'elderly' | null; intensity: number;
}
export interface Replica { speaker: 'party' | 'operator' | 'system'; text: string; remarks?: string[]; voice?: VoiceParams | null; hung_up?: boolean }
export interface PsyAct { code: string; title: string; quote: string }
export interface CallMessage {
  speaker: 'party' | 'operator' | 'system'; text: string; at: string; remarks?: string[];
  meta?: { acts?: PsyAct[]; level?: number; level_before?: number; level_after?: number } | null;
}
export interface CallPsy { profile: string; title: string; sensitive: boolean; start: number; level: number; peak: number; stage: string; paused: boolean; hung_up: boolean }
export interface CallView {
  id: string; role: string; party: 'applicant' | 'brigade' | 'service'; direction: 'in' | 'out'; status: string; aon: string;
  card_id: string | null; service_code: string | null; target_service: string | null;
  started_at: string; answered_at: string | null; ended_at: string | null; messages: CallMessage[];
  ended_by?: string | null; psy?: CallPsy | null;
}

const T = '/api/v1/training';
const post = <R,>(path: string, body: unknown = {}) => http<R>(`${T}${path}`, { method: 'POST', body: JSON.stringify(body) });

export const startIncomingCall = (b: { groups?: number[]; difficulty?: number } = {}) => post<CallStarted>('/calls/incoming', b);
export const answerCall = (id: string, cardId: string | null) => post<Replica | null>(`/calls/${id}/answer`, { card_id: cardId });
/** `signals` — задержка ответа и перебивание: их передаёт голосовой канал (дуплекс-адаптер); в тексте не нужны. */
export const sendReplica = (id: string, text: string, signals: { latency_ms?: number; interrupted?: boolean } = {}) =>
  post<Replica>(`/calls/${id}/replicas`, { text, ...signals });
export const endCall = (id: string) => post<{ status: string }>(`/calls/${id}/end`);
/** «Пауза» (п. 3.6): остановить тяжёлый учебный звонок; блок «Работа с заявителем» не оценивается. */
export const pauseCall = (id: string) => post<{ status: string }>(`/calls/${id}/pause`);
export const startDdsCall = (b: { card_id: string; service_code: string; party: CallView['party']; target_service?: string | null; incoming?: boolean }) =>
  post<CallStarted>('/calls/dds', b);
export const getCall = (id: string) => http<CallView>(`${T}/calls/${id}`);

// ------------------------------------------------------------------ голосовой ввод (п. 1.4): Whisper на сервере
export const useSpeechStatus = () =>
  useQuery({ queryKey: ['speech-status'], queryFn: () => http<{ enabled: boolean }>(`${T}/speech`), staleTime: 60_000 });
export async function transcribe(audio: Blob): Promise<string> {
  const body = new FormData();
  body.append('audio', audio, audio.type.includes('ogg') ? 'speech.ogg' : 'speech.webm');
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
  psy_profile?: string | null;
}
export interface ScenarioView {
  id: string; title: string; status: ScenarioRow['status']; difficulty: number; source: string;
  card_type_code: string; incident_type_code: string;
  legend: Record<string, unknown> & { opening?: string; what?: string; details?: string; facts?: Record<string, string>; persona?: Record<string, unknown> };
  reference_card: Record<string, unknown> & { final_type?: string; services?: { code: string; main: boolean }[] };
  reference_dds: Record<string, unknown>;
  psy_profile?: string | null;
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
// ------------------------------------------------------------------ п. 3.6: психологический модификатор
export interface PsyProfile {
  id: string; title: string; group: 'stress_reaction' | 'crisis' | 'caller_type'; sensitive: boolean; pinned_only: boolean;
  start: number; floor: number; pool: number; key_acts: string[]; critical: string[]; required_routing: string[];
  speech: Record<string, string>; sources: string[];
}
export const PSY_GROUP_TITLE: Record<PsyProfile['group'], string> = {
  stress_reaction: 'Острые стрессовые реакции (ЦЭПП МЧС)', crisis: 'Кризисные состояния', caller_type: 'Особые категории заявителей',
};
export interface PsySettings {
  enabled: boolean; share: number; profiles: string[] | 'auto'; intensity: 1 | 2 | 3; weight: number; sensitive: string[]; llm_acts: boolean;
}
export const PSY_DEFAULTS: PsySettings = { enabled: false, share: 0.3, profiles: 'auto', intensity: 2, weight: 0, sensitive: [], llm_acts: false };
export const usePsyProfiles = () =>
  useQuery({ queryKey: ['psy-profiles'], queryFn: () => http<PsyProfile[]>(`${T}/psy/profiles`), staleTime: 300_000 });
export const useSetScenarioPsy = () =>
  useInvalidating(({ id, profile }: { id: string; profile: string | null }) => post<{ status: string }>(`/scenarios/${id}/psy`, { profile }),
    [['scenarios'], ['scenario']]);
export const useEditScenario = () =>
  useInvalidating(({ id, ...b }: ScenarioEdit & { id: string }) => http<{ status: string }>(`${T}/scenarios/${id}`, { method: 'PATCH', body: JSON.stringify(b) }),
    [['scenarios'], ['scenario'], ['scenario-preview']]);

// ------------------------------------------------------------------ п. 4.2: занятия
export type SessionMode = 'cards_112' | 'dds_actions' | 'mixed';
export type CardSource = 'generated' | 'trainee' | 'mixed';
export interface SessionSettings {
  norm_112: number; norm_dds: number; threshold: number; difficulty: number;
  call_interval_s: number; feed_interval_s: number; max_waiting: number;
  psy?: PsySettings;
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
