/** Учебные материалы (п. 4.4): список, текст с найденными местами, загрузка, правка, удаление. */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, http } from './http';

export type MaterialKind = 'instruction' | 'memo' | 'classifier' | 'regulation' | 'other';
export const KIND_TITLE: Record<MaterialKind, string> = {
  instruction: 'инструкция', memo: 'памятка', classifier: 'классификатор', regulation: 'регламент', other: 'другое',
};
export interface MaterialRow {
  id: string; title: string; kind: MaterialKind; filename: string; file_type: 'pdf' | 'docx' | 'xlsx' | 'txt';
  size_bytes: number; visible: boolean; use_in_prompts: boolean; created_at: string | null; text_chars: number; uploaded_by_name: string | null;
}
export interface MaterialView {
  id: string; title: string; kind: MaterialKind; filename: string; file_type: MaterialRow['file_type']; content_type: string;
  visible: boolean; use_in_prompts: boolean; text: string; found: string[];
}

const M = '/api/v1/training/materials';
export const fileUrl = (id: string, download = false) => `${M}/${id}/file${download ? '?download=true' : ''}`;

export const useMaterials = (q: string) =>
  useQuery({ queryKey: ['materials', q], queryFn: () => http<MaterialRow[]>(`${M}?${new URLSearchParams({ q })}`) });
export const useMaterial = (id: string | null, q: string) =>
  useQuery({ queryKey: ['material', id, q], queryFn: () => http<MaterialView>(`${M}/${id}?${new URLSearchParams({ q })}`), enabled: !!id });

/** Загрузка — multipart/form-data: заголовок Content-Type ставит браузер (с границей), поэтому не через http(). */
export function useUploadMaterial() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (f: { file: File; title: string; kind: MaterialKind; visible: boolean; use_in_prompts: boolean }) => {
      const body = new FormData();
      body.set('file', f.file);
      body.set('title', f.title);
      body.set('kind', f.kind);
      body.set('visible', String(f.visible));
      body.set('use_in_prompts', String(f.use_in_prompts));
      const res = await fetch(M, { method: 'POST', body, credentials: 'same-origin' });
      if (!res.ok) {
        const b = await res.json().catch(() => ({}));
        const detail = Array.isArray(b.detail) ? b.detail.map((d: { msg: string }) => d.msg).join('; ') : undefined;
        throw new ApiError(res.status, b.error ?? 'http_error', b.message ?? detail ?? res.statusText);
      }
      return (await res.json()) as { id: string };
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['materials'] }),
  });
}

export function useUpdateMaterial() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...b }: { id: string; title?: string; kind?: MaterialKind; visible?: boolean; use_in_prompts?: boolean }) =>
      http<{ status: string }>(`${M}/${id}`, { method: 'PATCH', body: JSON.stringify(b) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['materials'] }); qc.invalidateQueries({ queryKey: ['material'] }); },
  });
}

export function useDeleteMaterial() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => http<void>(`${M}/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['materials'] }),
  });
}
