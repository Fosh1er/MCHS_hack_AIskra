/** Модуль dictionaries: типы «Что случилось?», опросные карты, службы, территория, перечисления. */
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { http } from './http';

export interface CardType {
  code: string; title: string; kind: 'incident' | 'service'; group_id: number | null;
  sign1: string[]; synonyms: string[]; quick: boolean; significant: boolean;
}
export interface TreeNode { label: string; codes: string[]; children: TreeNode[] }
export interface Questionnaire { card_type: CardType; roots: TreeNode[]; types_count: number }
export interface RoutingCell {
  col: number; service: string; service_short: string | null; recipient: string | null;
  flag: string | null; base: string | null; audience: string; delivery: string; service_type: string | null;
}
export interface IncidentTypeDetails {
  type: { code: string; final_type: string | null; ekp_type: string | null; main_services: string[] };
  routing: RoutingCell[];
}
export interface ServiceRow { code: string; short: string; full: string; kind: string; okrug: string | null; phone: string; integrated: boolean }
export interface ResolvedService { code: string; short: string; full: string; kind: string; phone: string; main: boolean; integrated: boolean; service_type: string | null; reasons: string[] }
export interface ResolvedServices { services: ResolvedService[]; monitoring: string[]; needs_address: boolean }
export interface Okrug { code: string; short: string; name: string; prefecture: string | null }
export interface District { code: string; name: string; okrug: string; kind: string; dds: string; aliases: string[] }
export interface Territory { okrugs: Okrug[]; districts: District[] }
export interface EnumValue { domain: string; code: string; name: string; sort: number; attrs: Record<string, unknown> }

const D = '/api/v1/dictionaries';
const forever = { staleTime: Infinity, gcTime: Infinity } as const;
const qs = (params: Record<string, string | string[] | undefined | null>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (Array.isArray(v)) v.forEach((x) => p.append(k, x));
    else if (v) p.set(k, v);
  }
  return p.toString();
};

export const useCardTypes = () => useQuery({ queryKey: ['dict', 'card-types'], queryFn: () => http<CardType[]>(`${D}/card-types`), ...forever });

export const useCardTypeSearch = (q: string) =>
  useQuery({
    queryKey: ['dict', 'card-types', q],
    queryFn: () => http<CardType[]>(`${D}/card-types?${qs({ q })}`),
    enabled: q.trim().length > 0,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });

export const useQuestionnaire = (cardType: string) =>
  useQuery({ queryKey: ['dict', 'questionnaire', cardType], queryFn: () => http<Questionnaire>(`${D}/card-types/${encodeURIComponent(cardType)}/questionnaire`), ...forever });

export const useIncidentType = (code: string | null) =>
  useQuery({ queryKey: ['dict', 'incident-type', code], queryFn: () => http<IncidentTypeDetails>(`${D}/incident-types/${code}`), enabled: !!code, ...forever });

export const useResolvedServices = (types: string[], flags: string[], okrug: string | null, district: string | null) =>
  useQuery({
    queryKey: ['dict', 'resolve', types, flags, okrug, district],
    queryFn: () => http<ResolvedServices>(`${D}/services/resolve?${qs({ incident_type: types, flag: flags, okrug, district })}`),
    enabled: types.length > 0,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });

export const useServices = () => useQuery({ queryKey: ['dict', 'services'], queryFn: () => http<ServiceRow[]>(`${D}/services`), ...forever });
export const useTerritory = () => useQuery({ queryKey: ['dict', 'territory'], queryFn: () => http<Territory>(`${D}/territory`), ...forever });
export const useEnum = (domain: string) => useQuery({ queryKey: ['dict', 'enum', domain], queryFn: () => http<EnumValue[]>(`${D}/enums/${domain}`), ...forever });
