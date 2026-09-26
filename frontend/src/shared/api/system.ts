/** Модуль system. CQRS на фронте: запросы — useQuery, команды — useMutation. */
import { useMutation, useQuery } from '@tanstack/react-query';
import { http } from './http';

export interface TaskInfo { task: string; provider: string; model: string; temperature: number; cache_mode: string; cache_ttl_s: number }
export interface AIConfig { allow_external: boolean; default_provider: string; tasks: TaskInfo[] }
export interface ProbeResult { task: string; provider: string; model: string; text: string; cached: boolean; latency_ms: number }
export interface Health { status: string; db: string; ai: { cache: { hits: number; misses: number; hit_rate: number } } }

export const useHealth = () => useQuery({ queryKey: ['health'], queryFn: () => http<Health>('/health'), refetchInterval: 10_000 });
export const useAIConfig = () => useQuery({ queryKey: ['system', 'ai'], queryFn: () => http<AIConfig>('/api/v1/system/ai') });
export const useProbeModel = () =>
  useMutation({
    mutationFn: (body: { prompt: string; task?: string }) =>
      http<ProbeResult>('/api/v1/system/ai/probe', { method: 'POST', body: JSON.stringify(body) }),
  });
