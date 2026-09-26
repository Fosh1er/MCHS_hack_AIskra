/** Панель администратора (п. 5.2): пользователи, группы, настройки, копии, состояние, логи, импорт. */
import { useMutation, useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query';
import { http } from './http';
import type { Role } from './auth';

export interface UserRow {
  id: string; login: string; full_name: string; role: Role; status: 'active' | 'blocked';
  operator_number: string | null; locked_until: string | null; last_login_at: string | null; created_at: string;
}
export interface GroupMember { user_id: string; member_role: '112' | 'dds'; dds_service_code: string | null; full_name?: string; login?: string }
export interface Group { id: string; name: string; members: GroupMember[] }
export interface ServiceState { name: string; state: 'ok' | 'warn' | 'critical' | 'off'; metrics: [string, string][]; note: string }
export interface BackupInfo { name: string; size_bytes: number; created_at: string; tables: number; rows: number }
export interface LogRecord { at: string; level: string; logger: string; message: string }
export type Settings = Record<'session_defaults' | 'backup', Record<string, number>>;
export type Limits = Record<string, Record<string, [number, number, number]>>;

const U = '/api/v1/users';
const S = '/api/v1/system';
const json = (method: string, body?: unknown): RequestInit => ({ method, body: body === undefined ? undefined : JSON.stringify(body) });

function useInvalidate<V, R>(fn: (v: V) => Promise<R>, keys: string[][]) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => keys.forEach((k) => qc.invalidateQueries({ queryKey: k })) });
}

export const ROLE_TITLE: Record<Role, string> = { admin: 'администратор', teacher: 'преподаватель', student: 'обучающийся' };

export const useUsers = (f: { q: string; role: string; status: string; page: number }) =>
  useQuery({
    queryKey: ['users', f],
    queryFn: () => {
      const p = new URLSearchParams({ q: f.q, limit: '50', offset: String((f.page - 1) * 50) });
      if (f.role) p.set('role', f.role);
      if (f.status) p.set('status', f.status);
      return http<{ items: UserRow[]; total: number }>(`${U}?${p}`);
    },
    placeholderData: keepPreviousData,
  });
export const useCreateUser = () =>
  useInvalidate((b: { login: string; full_name: string; role: Role; password: string; operator_number?: string | null }) => http<{ id: string }>(U, json('POST', b)), [['users']]);
export const useUpdateUser = () =>
  useInvalidate(({ id, ...b }: { id: string; full_name?: string; role?: Role; operator_number?: string | null }) => http<{ changed: string[] }>(`${U}/${id}`, json('PATCH', b)), [['users']]);
export const useSetBlocked = () =>
  useInvalidate(({ id, blocked, reason }: { id: string; blocked: boolean; reason?: string }) =>
    http<void>(`${U}/${id}/${blocked ? 'block' : 'unblock'}`, json('POST', blocked ? { reason: reason ?? '' } : undefined)), [['users']]);
export const useResetPassword = () =>
  useInvalidate(({ id, password }: { id: string; password: string }) => http<void>(`${U}/${id}/password`, json('POST', { new_password: password })), [['users']]);

export const useGroups = (enabled = true) => useQuery({ queryKey: ['groups'], queryFn: () => http<Group[]>('/api/v1/groups'), enabled });
export const useSaveGroup = () =>
  useInvalidate(({ id, ...b }: { id?: string; name: string; members: GroupMember[] }) =>
    http<{ id: string }>(id ? `/api/v1/groups/${id}` : '/api/v1/groups', json(id ? 'PUT' : 'POST', {
      name: b.name, members: b.members.map((m) => ({ user_id: m.user_id, member_role: m.member_role, dds_service_code: m.member_role === 'dds' ? m.dds_service_code : null })),
    })), [['groups']]);
export const useDeleteGroup = () => useInvalidate((id: string) => http<void>(`/api/v1/groups/${id}`, json('DELETE')), [['groups']]);

export const useStatus = () => useQuery({ queryKey: ['system', 'status'], queryFn: () => http<ServiceState[]>(`${S}/status`), refetchInterval: 15_000 });
export const useSettings = () => useQuery({ queryKey: ['system', 'settings'], queryFn: () => http<Settings>(`${S}/settings`) });
export const useLimits = () => useQuery({ queryKey: ['system', 'limits'], queryFn: () => http<Limits>(`${S}/settings/limits`), staleTime: Infinity });
export const useSaveSettings = () =>
  useInvalidate(({ key, values }: { key: string; values: Record<string, number> }) => http<Record<string, number>>(`${S}/settings/${key}`, json('PUT', { values })), [['system', 'settings']]);
export const useBackups = () => useQuery({ queryKey: ['system', 'backups'], queryFn: () => http<BackupInfo[]>(`${S}/backups`) });
export const useCreateBackup = () => useInvalidate(() => http<BackupInfo>(`${S}/backups`, json('POST')), [['system', 'backups'], ['system', 'status']]);
export const restoreBackup = (name: string, confirm: string) => http<BackupInfo>(`${S}/backups/${name}/restore`, json('POST', { confirm }));
export const backupUrl = (name: string) => `${S}/backups/${name}`;
export const useLogs = (level: string, q: string) =>
  useQuery({ queryKey: ['system', 'logs', level, q], queryFn: () => http<LogRecord[]>(`${S}/logs?${new URLSearchParams({ level, q, limit: '300' })}`), refetchInterval: 10_000 });

export interface ImportReport { source_file: string; counts: Record<string, number>; deactivated?: Record<string, number>; warnings: string[] }
export const useImport = () =>
  useMutation({ mutationFn: (what: 'dictionaries' | 'addresses') => http<ImportReport>(what === 'dictionaries' ? '/api/v1/dictionaries/import' : '/api/v1/dictionaries/addresses/import', json('POST')) });
