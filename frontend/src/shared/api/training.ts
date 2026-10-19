/** Модуль training: учебные звонки (п. 1.4, 2.3), банк сценариев (п. 3.2, 4.1) и занятия (п. 4.2). */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, http } from './http';

export interface CallStarted { call_id: string; scenario_id: string | null; aon: string; channel: string; warning?: string | null }
/** Параметры голоса профиля заявителя (п. 3.7): для синтеза речи и дуплекс-адаптера. */
export interface VoiceParams {
  profile: string; direction: 'up' | 'down'; level: number; rate: number; pitch_st: number; gain_db: number;
  nonverbal: string[]; scene: string | null; voice: 'child' | 'elderly' | null; intensity: number;
}
export interface PsyAct { code: string; title: string; quote: string }
export interface CallPsy { profile: string; title: string; sensitive: boolean; start: number; level: number; peak: number; stage: string; paused: boolean; hung_up: boolean }
/** Что изменило состояние заявителя: код правила и сработавший фрагмент реплики оператора (п. 3.6). */
export interface ToneChange { reason: 'calming' | 'invalidating' | 'pressure' | 'on_topic' | 'situation'; fragment: string; tension: number; trust: number; readiness: number }
/** Состояние ИИ-заявителя у его реплики (п. 3.6): шкалы 0–10 и подача голоса. Фактов легенды здесь нет. */
export interface Tone {
  emotion: string; emotion_title: string; tension: number; trust: number; readiness: number; band: 'calm' | 'tense' | 'panic';
  pace: 'slow' | 'normal' | 'fast' | 'very_fast'; volume: 'whisper' | 'low' | 'normal' | 'loud'; breathing: string; changes: ToneChange[];
}
export interface Replica {
  speaker: 'party' | 'operator' | 'system'; text: string; message_id?: string | null; tone?: Tone | null;
  remarks?: string[]; voice?: VoiceParams | null; hung_up?: boolean; // п. 3.7
}
export interface CallMessage {
  speaker: 'party' | 'operator' | 'system'; text: string; at: string; id?: string | null; tone?: Tone | null;
  remarks?: string[]; meta?: { acts?: PsyAct[]; level?: number; level_before?: number; level_after?: number } | null; // п. 3.7
}
export interface CallView {
  id: string; role: string; party: 'applicant' | 'brigade' | 'service'; direction: 'in' | 'out'; status: string; aon: string;
  card_id: string | null; service_code: string | null; target_service: string | null;
  started_at: string; answered_at: string | null; ended_at: string | null; messages: CallMessage[]; tone?: Tone | null;
  mode?: ReplicaVia; // как оператор вёл разговор: самый «голосовой» из способов его реплик
  ended_by?: string | null; psy?: CallPsy | null; // п. 3.7
  branching?: boolean; branch?: BranchDebrief | null; // F5: ветвящийся сценарий — таймер /tick и «Итог ситуации»
}

// ------------------------------------------------------------------ F5: ветвящиеся сценарии (ADR-0014)
export type OutcomeCode = 'favorable' | 'partial' | 'adverse' | 'tragic';
export const OUTCOME_TITLE: Record<OutcomeCode, string> = {
  favorable: 'благоприятный', partial: 'частично благоприятный', adverse: 'неблагоприятный', tragic: 'трагический',
};
export interface BranchChoice { label: string; effect: string; to: string; to_title: string; source: string; didactic: boolean; outcome: OutcomeCode | null }
export interface BranchFork { node: string; title: string; at_s: number; decided_s: number | null; taken: BranchChoice | null; others: BranchChoice[] }
/** «Итог ситуации»: итог, путь по узлам, развилки «что сделали / что было бы», источники. `final` — окончательный. */
export interface BranchDebrief {
  template: string; title: string; node: string; node_title: string; situation?: string;
  outcome: { code: OutcomeCode; title: string; text: string; sources: string[] } | null;
  path: { node: string; title: string; at_s: number }[];
  forks: BranchFork[];
  decisions: Record<string, number>;
  instructions: { id: string; title: string; harmful: boolean; said_s: number | null; source: string }[];
  sources: Record<string, { title: string; url: string }>;
  final: boolean; weight?: number; score?: number | null;
}
export interface BranchTemplate { id: string; title: string; description: string; incident_codes: string[]; forks: number; outcomes: OutcomeCode[] }
interface BranchEdgeRaw { to: string; when: Record<string, string | number | boolean>; label: string; effect: string; source: string; note?: string }
/** Граф ситуации в сценарии (копия шаблона) — для просмотра преподавателем. */
export interface BranchGraph {
  id: string; title: string; description?: string; start: string; horizon_s: number;
  nodes: Record<string, { title: string; situation?: string; event?: string; edges?: BranchEdgeRaw[]; outcome?: { code: OutcomeCode; text: string; sources: string[] } }>;
  instructions: Record<string, { title: string; stems: string[]; source: string; harmful?: boolean }>;
  sources: Record<string, { title: string; url: string }>;
}

const T = '/api/v1/training';
const post = <R,>(path: string, body: unknown = {}) => http<R>(`${T}${path}`, { method: 'POST', body: JSON.stringify(body) });

export const startIncomingCall = (b: { groups?: number[]; difficulty?: number } = {}) => post<CallStarted>('/calls/incoming', b);
export const answerCall = (id: string, cardId: string | null) => post<Replica | null>(`/calls/${id}/answer`, { card_id: cardId });
/** Как оператор сказал реплику (п. 3.6): напечатал, кнопкой «говорить» или без рук — режим звонка видит отчёт. */
export type ReplicaVia = 'text' | 'voice' | 'hands_free';
/** `signals` (п. 3.7) — задержка ответа и перебивание: их передаёт голосовой канал; в тексте не нужны. */
export const sendReplica = (id: string, text: string, via: ReplicaVia = 'text', signals: { latency_ms?: number; interrupted?: boolean } = {}) =>
  post<Replica>(`/calls/${id}/replicas`, { text, via, ...signals });
/** «Пауза» (п. 3.7): остановить тяжёлый учебный звонок; блок «Работа с заявителем» не оценивается. */
export const pauseCall = (id: string) => post<{ status: string }>(`/calls/${id}/pause`);
export const endCall = (id: string) => post<{ status: string }>(`/calls/${id}/end`);
export const startDdsCall = (b: { card_id: string; service_code: string; party: CallView['party']; target_service?: string | null; incoming?: boolean }) =>
  post<CallStarted>('/calls/dds', b);
export const getCall = (id: string) => http<CallView>(`${T}/calls/${id}`);
/** F5: таймер ситуации — пока звонок идёт, раз в 5 с; ответ — реплики-события, если ситуация изменилась сама. */
export const tickCall = (id: string) => post<Replica[]>(`/calls/${id}/tick`);
export const useBranchTemplates = () =>
  useQuery({ queryKey: ['branch-templates'], queryFn: () => http<BranchTemplate[]>(`${T}/branch-templates`), staleTime: 300_000 });

// ------------------------------------------------------------------ речь: голосовой ввод (п. 1.4) и голос собеседника (п. 3.6)
/** `enabled` — распознавание (кнопка «говорить»); `tts` — серверный синтез, иначе озвучивает браузер. */
export const useSpeechStatus = () =>
  useQuery({ queryKey: ['speech-status'], queryFn: () => http<{ enabled: boolean; tts: boolean }>(`${T}/speech`), staleTime: 60_000 });
/** Звук реплики собеседника — адрес своего сайта: CSP стенда не пускает `blob:` в медиа (п. 3.6). */
export const replicaAudioUrl = (callId: string, messageId: string) => `${T}/calls/${callId}/messages/${messageId}/audio`;

/** F1: ответ собеседника потоком. Что показано до `final` — черновик; сохранён в звонке именно `final`. */
export interface StreamMetrics {
  source: 'llm' | 'rules'; model: string | null; ttft_ms: number | null; total_ms: number;
  pieces: number; pieces_per_s: number | null; replaced: boolean;
}
/** Состояние заявителя с профилем (п. 3.7) до ответа: уровень ECCS 1–5 и что его изменило. */
export interface PsyLive {
  level_before: number; level_after: number; level_title: string; stage: string;
  acts: { code: string; title: string }[]; deltas: { cause: string; change: number; note: string }[];
}
export type StreamedReplica = Replica & { metrics: StreamMetrics };
export type StreamEvent =
  | { type: 'state'; tone?: Tone; psy?: PsyLive }
  | { type: 'model'; model: string; provider: string }
  | { type: 'token'; text: string }
  | { type: 'remark'; text: string }
  | { type: 'replace'; reason: string };

/** Реплика оператора → ответ потоком SSE (`POST /calls/{id}/replicas/stream`). Сервер без потока (404/405) —
 *  `ApiError` со статусом, вызывающий отправит реплику обычным запросом. */
export async function streamReplica(
  id: string, text: string, via: ReplicaVia, signals: { latency_ms?: number; interrupted?: boolean },
  onEvent: (e: StreamEvent) => void,
): Promise<StreamedReplica> {
  const res = await fetch(`${T}/calls/${id}/replicas/stream`, {
    method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, via, ...signals }),
  });
  if (!res.ok || !res.body) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.error ?? 'http_error', body.message ?? res.statusText);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  for (;;) {
    const { done, value } = await reader.read();
    buf += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    let cut = buf.indexOf('\n\n');
    while (cut >= 0) {
      const block = buf.slice(0, cut);
      buf = buf.slice(cut + 2);
      cut = buf.indexOf('\n\n');
      const kind = /^event: (.*)$/m.exec(block)?.[1];
      const raw = /^data: (.*)$/m.exec(block)?.[1];
      if (!kind || raw === undefined) continue;
      const data = JSON.parse(raw);
      if (kind === 'final') return data as StreamedReplica;
      if (kind === 'error') throw new ApiError(422, data.code ?? 'stream_error', data.message ?? 'Ответ не получен');
      if (kind === 'state') onEvent({ type: 'state', tone: data.tone, psy: data.level_after ? data : undefined });
      else if (kind === 'model') onEvent({ type: 'model', model: data.model, provider: data.provider });
      else if (kind === 'token' || kind === 'remark') onEvent({ type: kind, text: data.text });
      else if (kind === 'replace') onEvent({ type: 'replace', reason: data.reason });
    }
    if (done) throw new ApiError(502, 'stream_cut', 'Соединение прервалось до конца ответа');
  }
}

/** Звук фразы ответа, который ещё генерируется (F1): голос роли звонка, подача — по состоянию заявителя. */
export const speakUrl = (callId: string, text: string, tone?: Tone | null) => {
  const q = new URLSearchParams({ text });
  if (tone) { q.set('emotion', tone.emotion); q.set('pace', tone.pace); q.set('volume', tone.volume); q.set('breathing', tone.breathing); }
  return `${T}/calls/${callId}/speak?${q}`;
};
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
  psy_profile?: string | null;
  review_accepted?: number; review_rework?: number; review_total?: number; // п. 3.3: разделы эталона
  branching?: string | null; // F5: шаблон ветвления
}
/** Решение преподавателя по разделу эталона (п. 3.3); `stale` — раздел изменили после решения. */
export interface SectionReview { key: string; title: string; decision: 'accepted' | 'rework' | null; comment: string; stale: boolean; at: string | null }
export interface ScenarioView {
  id: string; title: string; status: ScenarioRow['status']; difficulty: number; source: string;
  card_type_code: string; incident_type_code: string;
  legend: Record<string, unknown> & { opening?: string; what?: string; details?: string; facts?: Record<string, string>; persona?: Record<string, unknown> };
  reference_card: Record<string, unknown> & { final_type?: string; services?: { code: string; main: boolean }[] };
  reference_dds: Record<string, unknown>;
  psy_profile?: string | null;
  review?: SectionReview[];
  branching?: BranchGraph | null; // F5: граф ситуации
}
export interface PreviewItem { question: string; answer: string; reference: string }
export interface ScenarioFilter { status?: string; difficulty?: number; card_type?: string; source?: string; psy?: string; page: number; page_size: number }

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
  useInvalidating((b: { count: number; groups: number[]; difficulty: number; branching?: string | null }) => post<{ ids: string[] }>('/scenarios/generate', b), [['scenarios']]);
export const useReviewScenario = () =>
  useInvalidating(({ id, approve }: { id: string; approve: boolean }) => post<{ status: string }>(`/scenarios/${id}/${approve ? 'approve' : 'archive'}`), [['scenarios'], ['scenario']]);
export type SectionDecision = { decision: 'accepted' | 'rework'; comment?: string };
export const useReviewSections = () =>
  useInvalidating(({ id, sections }: { id: string; sections: Record<string, SectionDecision> }) =>
    post<{ status: string; sections: SectionReview[] }>(`/scenarios/${id}/review`, { sections }), [['scenarios'], ['scenario']]);
export interface ScenarioEdit { title?: string; difficulty?: number; opening?: string; what?: string; details?: string; comment?: string }
// ------------------------------------------------------------------ п. 3.7: психологический модификатор
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
/** Методика модификатора (F4): основа, шкала ECCS, профили карточками и реестр источников — всё из каталога. */
export interface PsySource { code: string; short: string; title: string; url: string | null; official: boolean; doc: string; section: string }
export interface PsyActItem { code: string; title: string; key: boolean; critical: boolean }
export interface PsyProfileCard {
  id: string; title: string; group: PsyProfile['group']; group_title: string; sensitive: boolean; start: number; floor: number; deescalates: boolean;
  signs: { level: number; title: string; text: string }[]; does: PsyActItem[]; donts: PsyActItem[]; routing: string[]; sources: string[];
}
export interface PsyMethodology {
  version: number; scale: { level: number; title: string }[]; basis: { source: PsySource; use: string }[];
  profiles: PsyProfileCard[]; sources: Record<string, PsySource>;
}
export const usePsyMethodology = () =>
  useQuery({ queryKey: ['psy-methodology'], queryFn: () => http<PsyMethodology>(`${T}/psy/methodology`), staleTime: Infinity });
export const useSetScenarioPsy = () =>
  useInvalidating(({ id, profile }: { id: string; profile: string | null }) => post<{ status: string }>(`/scenarios/${id}/psy`, { profile }),
    [['scenarios'], ['scenario']]);
export interface GrammarRemark { field: string; quote: string; fix: string; rule: string }
export interface EditScenarioResult { status: string; grammar: GrammarRemark[]; checked_by: 'rules' | 'rules+model' }
export const useEditScenario = () =>
  useInvalidating(({ id, ...b }: ScenarioEdit & { id: string }) => http<EditScenarioResult>(`${T}/scenarios/${id}`, { method: 'PATCH', body: JSON.stringify(b) }),
    [['scenarios'], ['scenario'], ['scenario-preview']]);

// ------------------------------------------------------------------ п. 4.2: занятия
export type SessionMode = 'cards_112' | 'dds_actions' | 'mixed';
export type CardSource = 'generated' | 'trainee' | 'mixed';
export interface SessionSettings {
  norm_112: number; norm_dds: number; threshold: number; difficulty: number;
  call_interval_s: number; feed_interval_s: number; max_waiting: number;
  psy?: PsySettings;
  branch?: { weight: number }; // F5: вес блока «Развитие ситуации»; 0 — информативно
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
