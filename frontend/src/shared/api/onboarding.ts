/** Обучение интерфейсу (п. 5.3, 5.4): прогресс хранится на сервере за учётной записью — занятия идут на разных АРМ. */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { http } from './http';

/** Чьи подсказки показывать сами — сервер решает по правам (п. 5.4). */
export type Audience = 'student' | 'teacher';

export interface OnboardingState {
  enabled: boolean; // показывать автоматически (есть аудитория)
  audience: Audience | null;
  dismissed: boolean; // «пропустить обучение»
  seen: string[]; // пройденные экраны
}

/** `seen` с `tours` — несколько экранов одной записью: обзор и первый экран отмечаются вместе (п. 5.4). */
export type OnboardingAction = { action: 'seen'; tours: string[] } | { action: 'dismiss' } | { action: 'reset' };

const KEY = ['auth', 'onboarding'] as const;
const URL = '/api/v1/auth/onboarding';

export const useOnboarding = (enabled: boolean) =>
  useQuery({ queryKey: KEY, queryFn: () => http<OnboardingState>(URL), enabled, staleTime: Infinity });

export const useUpdateOnboarding = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: OnboardingAction) => http<OnboardingState>(URL, { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: (state) => qc.setQueryData(KEY, state),
  });
};
