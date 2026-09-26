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
