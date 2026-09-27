/** Модуль assessment: автооценка по эталону (п. 3.4), отчёт по занятию, экспертная правка и прогресс (п. 4.3). */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, http } from './http';

export interface CriterionResult { key: string; title: string; score: number | null; errors: string[]; note: string }
export interface Assessment {
  id: string; card_id: string; student_id: string | null; role: '112' | 'dds'; service_code: string | null;
  score: number; passed: boolean; grader: string; created_at: string | null;
  details: {
    criteria: CriterionResult[]; errors: string[]; has_reference: boolean; card_number: number; stats: Record<string, number | null>; version?: number;
    expert?: { score: number; comment: string; teacher_id: string; auto_score: number };
  };
}
export interface Insights {
  assessments: number; average_score: number; passed_share: number;
  weakest: { key: string; title: string; average: number; checked: number }[];
  frequent_errors: { text: string; count: number }[];
}

const A = '/api/v1/assessment';
const key = (cardId: string, role: string, service?: string | null) => ['assessment', cardId, role, service ?? ''];

export const useAssessment = (cardId: string, role: '112' | 'dds', service?: string | null) =>
  useQuery({
    queryKey: key(cardId, role, service),
    queryFn: async () => {
      try {
        const p = new URLSearchParams({ role });
        if (service) p.set('service_code', service);
        return await http<Assessment>(`${A}/cards/${cardId}?${p}`);
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null; // оценки ещё нет
        throw e;
      }
    },
  });

export function useEvaluate(cardId: string, role: '112' | 'dds', service?: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => http<Assessment>(`${A}/cards/${cardId}/evaluate`, { method: 'POST', body: JSON.stringify({ role, service_code: service ?? null }) }),
    onSuccess: (a) => qc.setQueryData(key(cardId, role, service), a),
  });
}

export const useInsights = (enabled: boolean) =>
  useQuery({ queryKey: ['assessment', 'insights'], queryFn: () => http<Insights>(`${A}/insights`), enabled, refetchInterval: 30_000 });

// ------------------------------------------------------------------ п. 4.3: отчёт по занятию
export interface CardResult {
  card_id: string; card_number: number; card_types: string[]; processing_s: number | null; norm_s: number; deviation_s: number | null;
  assessment_id: string | null; score: number | null; passed: boolean | null; expert: boolean; expert_comment: string; errors: string[];
  criteria: Record<string, number | null>;
}
export interface StudentReport {
  student_id: string; full_name: string; role: '112' | 'dds'; service_code: string | null; cards: CardResult[];
  avg_score: number | null; passed_share: number | null; avg_time_s: number | null; not_assessed: number;
}
export interface SessionReport {
  session_id: string; title: string; mode: string; status: string; started_at: string | null; finished_at: string | null;
  settings: Record<string, number>; students: StudentReport[]; avg_score: number | null; passed_share: number | null; cards_count: number;
  heatmap: { criteria: { key: string; title: string }[]; rows: { student: string; role: string; values: Record<string, number> }[] };
  time_buckets: { label: string; count: number }[];
  score_series: { t: string; v: number; who: string }[];
}
export interface ProgressView {
  points: { t: string; v: number; role: string; card_number: number | null; passed: boolean }[];
  avg_score: number | null; weakest: { key: string; title: string; average: number }[]; recent_errors: string[];
  expert_comments: { card_number: number | null; score: number; comment: string }[];
  recommendations: Recommendation[];
}

export const useSessionReport = (id: string) =>
  useQuery({ queryKey: ['report', id], queryFn: () => http<SessionReport>(`${A}/sessions/${id}/report`) });
export const reportCsvUrl = (id: string) => `${A}/sessions/${id}/report.csv`;

export function useEvaluateSession(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => http<{ assessed: number; skipped: number }>(`${A}/sessions/${id}/evaluate`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['report', id] }),
  });
}

export function useOverride(sessionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, score, comment, threshold }: { id: string; score: number; comment: string; threshold?: number }) =>
      http<Assessment>(`${A}/${id}/override`, { method: 'POST', body: JSON.stringify({ score, comment, threshold }) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['report', sessionId] });
      qc.invalidateQueries({ queryKey: ['assessment'] });
    },
  });
}

export const useMyProgress = () => useQuery({ queryKey: ['my-progress'], queryFn: () => http<ProgressView>(`${A}/my/progress`) });

export interface Recommendation { key: string; average: number; text: string }
export interface MySessionReport { report: SessionReport; recommendations: Recommendation[] }
export const useMySessionReport = (id: string) =>
  useQuery({ queryKey: ['my-report', id], queryFn: () => http<MySessionReport>(`${A}/sessions/${id}/mine`) });

// ------------------------------------------------------------------ аналитика преподавателя (specs/4.5)
/** «Норматив / факт» (ПП РФ № 1931; форма 1/112): у каждого занятия может быть свой норматив. */
export interface NormStat {
  count: number; within: number; within_share: number | null;
  median_s: number | null; p90_s: number | null; avg_s: number | null; norm_s: number | null;
}
export interface NormReportView {
  period: string; source: string; card_112: NormStat; dds: NormStat;
  by_student: { key: string; title: string; role: '112' | 'dds'; stat: NormStat }[];
  by_session: { session_id: string; title: string; at: string | null; card_112: NormStat; dds: NormStat }[];
}
export interface ErrorRow { text: string; count: number; cards: number[]; students: string[] }
export interface GroupRow { group_id: number; title: string; cards: number; avg_score: number | null; errors: number }
export interface StudentProfileView {
  student_id: string; full_name: string; roles: ('112' | 'dds')[]; sessions: number; cards: number;
  avg_score: number | null; passed_share: number | null;
  points: { t: string; v: number; role: string; card_number: number; session: string; passed: boolean | null }[];
  criteria: { key: string; title: string; student: number; group: number | null; delta: number | null }[];
  frequent_errors: ErrorRow[]; coverage: GroupRow[];
  not_practiced: { group_id: number; title: string; approved: number }[];
  by_difficulty: { difficulty: number; cards: number; avg_score: number | null }[];
  card_112: NormStat; dds: NormStat; recommendations: Recommendation[]; readiness: ReadinessRow[];
}
export interface DebriefView {
  session_id: string; title: string; started_at: string | null; cards: number; assessed: number;
  avg_score: number | null; passed_share: number | null; top_errors: ErrorRow[];
  weak_criteria: { key: string; title: string; average: number; advice: string }[];
  weak_groups: GroupRow[];
  overdue: { who: string; role: '112' | 'dds'; card_number: number; time_s: number; norm_s: number }[];
  best: { who: string; role: '112' | 'dds'; avg_score: number | null }[];
  card_112: NormStat; dds: NormStat;
}
export interface AssignmentSuggestion {
  title: string; mode: 'cards_112' | 'dds_actions' | 'mixed';
  groups: { group_id: number; title: string; reason: string; avg_score: number | null; approved: number }[];
  difficulty: number; difficulty_reason: string;
  focus: { key: string; title: string; average: number; advice: string }[];
  participants: { student_id: string; full_name: string; role: '112' | 'dds'; service_code: string | null }[];
  approved_total: number; warnings: string[];
}

export const useNormReport = (days: number | null) =>
  useQuery({
    queryKey: ['analytics', 'norms', days],
    queryFn: () => http<NormReportView>(`${A}/analytics/norms?days=${days ?? 0}`), // 0 — все занятия
  });
export const useStudentProfile = (id: string) =>
  useQuery({ queryKey: ['analytics', 'student', id], queryFn: () => http<StudentProfileView>(`${A}/analytics/students/${id}`) });
export const useDebrief = (id: string) =>
  useQuery({ queryKey: ['analytics', 'debrief', id], queryFn: () => http<DebriefView>(`${A}/sessions/${id}/debrief`) });
export const fetchSuggestion = (studentIds: string[]) =>
  http<AssignmentSuggestion>(`${A}/analytics/suggest?${studentIds.map((id) => `student_id=${encodeURIComponent(id)}`).join('&')}`);

// ------------------------------------------------------------------ готовность к допуску (specs/4.6)
export interface Readiness {
  grade: 5 | 4 | 3 | 2 | null; grade_label: string; ready: boolean; status: string; cards: number;
  avg_score: number | null; timing: string; within_share: number | null; p90_ratio: number | null; reasons: string[];
}
export interface ReadinessRow {
  student_id: string; full_name: string; role: '112' | 'dds'; service_code: string | null;
  sessions: number; groups: number; last_at: string | null; expert: number; readiness: Readiness;
}
export interface ReadinessView {
  rows: ReadinessRow[]; last: number; min_cards: number; generated_at: string; teacher: string;
  scale: { grade: string; rule: string }[]; source: string;
}
export const useReadiness = (p: { last: number; studentIds?: string[] }) =>
  useQuery({
    queryKey: ['analytics', 'readiness', p.last, p.studentIds ?? []],
    queryFn: () => http<ReadinessView>(`${A}/analytics/readiness?last=${p.last}${(p.studentIds ?? []).map((id) => `&student_id=${encodeURIComponent(id)}`).join('')}`),
  });
