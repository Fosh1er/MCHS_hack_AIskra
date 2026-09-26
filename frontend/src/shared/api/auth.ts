/** Модуль identity: вход, выход, текущий пользователь (п. 0.3). */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { http, isUnauthorized } from './http';

export type Role = 'admin' | 'teacher' | 'student';

export const PERMISSIONS = {
  usersManage: 'users.manage',
  auditRead: 'audit.read',
  systemManage: 'system.manage',
  trainingParticipate: 'training.participate',
  lessonsConduct: 'lessons.conduct',
} as const;

export interface Me {
  user_id: string;
  login: string;
  full_name: string;
  role: Role;
  role_title: string;
  operator_number: string | null;
  arm_number: string | null;
  permissions: string[];
}

export interface LoginInput { login: string; password: string; arm_number?: string }

const ME = ['auth', 'me'] as const;

/** Текущий пользователь. 401 — не ошибка, а «не выполнен вход» (data === null). */
export const useMe = () =>
  useQuery({
    queryKey: ME,
    queryFn: async () => {
      try {
        return await http<Me>('/api/v1/auth/me');
      } catch (e) {
        if (isUnauthorized(e)) return null;
        throw e;
      }
    },
    staleTime: 60_000,
    retry: false,
  });

export const useLogin = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: LoginInput) => http<Me>('/api/v1/auth/login', { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: (me) => {
      qc.clear();
      qc.setQueryData(ME, me);
    },
  });
};

export const useLogout = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => http<void>('/api/v1/auth/logout', { method: 'POST' }),
    onSettled: () => {
      qc.clear();
      qc.setQueryData(ME, null);
    },
  });
};

/** Стартовый раздел роли после входа. */
export function homeFor(me: Me): string {
  if (me.permissions.includes(PERMISSIONS.systemManage)) return '/admin';
  if (me.permissions.includes(PERMISSIONS.auditRead)) return '/admin/audit';
  if (me.role === 'teacher') return '/teacher';
  // обучающийся сразу попадает в «Список происшествий», как оператор в АРМ-112 (п. 1.3)
  if (me.permissions.includes(PERMISSIONS.trainingParticipate)) return '/arm/112/journal';
  return '/student';
}
