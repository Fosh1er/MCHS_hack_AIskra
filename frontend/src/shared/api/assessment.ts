/** Модуль assessment: автооценка карточки 112 и работы ДДС по эталону (п. 3.4). */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, http } from './http';

export interface CriterionResult { key: string; title: string; score: number | null; errors: string[]; note: string }
export interface Assessment {
  id: string; card_id: string; student_id: string | null; role: '112' | 'dds'; service_code: string | null;
  score: number; passed: boolean; grader: string; created_at: string | null;
  details: { criteria: CriterionResult[]; errors: string[]; has_reference: boolean; card_number: number; stats: Record<string, number | null>; version?: number };
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
