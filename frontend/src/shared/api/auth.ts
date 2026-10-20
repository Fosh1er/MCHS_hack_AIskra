/** Модуль identity: вход, выход, текущий пользователь (п. 0.3). */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, http, isUnauthorized } from './http';
import { isTransient } from './resilience';

export type Role = 'admin' | 'teacher' | 'student';

export const PERMISSIONS = {
  usersManage: 'users.manage',
  auditRead: 'audit.read',
  systemManage: 'system.manage',
  trainingParticipate: 'training.participate',
  lessonsConduct: 'lessons.conduct',
  scenariosManage: 'scenarios.manage',
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
  features?: Record<string, boolean>; // включённые возможности (настройки администратора): role_112
}

/** Роль оператора 112 включена администратором (по рекомендациям экспертов скрыта по умолчанию, приоритет — ДДС). */
export const role112 = (me?: Me | null) => me?.features?.role_112 !== false;

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
    // сбой связи (6.1): пока сервер недоступен — спрашиваем каждые 3 с, приложение оживёт само
    refetchInterval: (q) => (q.state.status === 'error' && isTransient(q.state.error) ? 3_000 : false),
    refetchIntervalInBackground: true,
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

/** Демо-стенд (F2): учётки для входа одной кнопкой. Пароль приходит, только если его показ включён на сервере. */
export interface DemoAccount {
  login: string;
  role: Role;
  title: string;
  full_name: string;
  hint: string[];
  arm_number: string | null;
}
export interface DemoAccounts { accounts: DemoAccount[]; password: string | null }

/** null — демо-входа нет (режим prod отвечает 404 или учёток нет): страница входа как обычно. */
export const useDemoAccounts = () =>
  useQuery({
    queryKey: ['auth', 'demo-accounts'] as const,
    queryFn: async () => {
      try {
        const data = await http<DemoAccounts>('/api/v1/auth/demo-accounts');
        return data.accounts.length ? data : null;
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
      }
    },
    staleTime: 5 * 60_000,
    retry: false,
  });

export const useDemoLogin = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (login: string) => http<Me>('/api/v1/auth/demo-login', { method: 'POST', body: JSON.stringify({ login }) }),
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
  // обучающийся сразу попадает в «Список происшествий», как оператор в АРМ-112 (п. 1.3);
  // на телефоне эмулятор неудобен (6.3) — в кабинет
  const narrow = typeof window !== 'undefined' && window.innerWidth < 1000;
  if (me.permissions.includes(PERMISSIONS.trainingParticipate)) return narrow ? '/student' : role112(me) ? '/arm/112/journal' : '/arm/dds';
  return '/student';
}
