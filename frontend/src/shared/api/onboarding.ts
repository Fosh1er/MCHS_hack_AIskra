/** Обучение интерфейсу (п. 5.3): прогресс хранится на сервере за учётной записью — занятия идут на разных АРМ. */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { http } from './http';

export interface OnboardingState {
  enabled: boolean; // показывать автоматически (обучающемуся)
  dismissed: boolean; // «пропустить обучение»
  seen: string[]; // пройденные экраны
}

export type OnboardingAction = { action: 'seen'; tour: string } | { action: 'dismiss' } | { action: 'reset' };

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
