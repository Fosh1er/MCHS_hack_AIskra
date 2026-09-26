/** Модуль incidents: карточка происшествия 112 (п. 1.1). */
import { useMutation, useQuery } from '@tanstack/react-query';
import { http } from './http';

export interface CardAddress {
  raw: string; country: string; region: string; city: string; object: string; okrug: string | null; district: string | null;
  street: string; house: string; building: string; structure: string; flat: string; entrance: string; floor: string;
  code: string; descriptive: string; lat: number | null; lon: number | null;
}
export interface CardData {
  phones: { aon: string; provided: string; on_site: string; foreign: boolean };
  channel: string | null;
  applicant: { name: string; status: string | null; foreign_language: boolean };
  victims: { has: boolean; count: number };
  card_types: string[];
  incident_types: string[];
  questionnaire: Record<string, Record<string, string>>;
  card_flags: string[];
  address: CardAddress;
  description: string;
  services?: string[];
  flags: { no_contact: boolean; call_dropped: boolean; refusal_103: boolean; emergency: boolean; incident: boolean };
}
export interface CardServiceIn { code: string; is_main: boolean; added_by: 'auto' | 'manual'; service_type?: string | null }
export interface CardOpened { id: string; number: number; opened_at: string }
export interface CardSaved { id: string; number: number; status: string; saved_at: string; processing_ms: number; services: CardServiceIn[] }
export interface CardView {
  id: string; number: number; status: string; author_id: string | null; author_name: string | null;
  operator_number: string | null; arm_number: string | null; opened_at: string | null; saved_at: string | null;
  processing_ms: number | null; data: Partial<CardData>;
  services: { code: string; short: string; integrated: boolean; is_main: boolean; added_by: string; status: string; status_at: string | null }[];
}

const I = '/api/v1/incidents/cards';

export const useOpenCard = () =>
  useMutation({ mutationFn: (body: { aon?: string; channel?: string | null }) => http<CardOpened>(I, { method: 'POST', body: JSON.stringify(body) }) });

export const useSaveCard = (id: string) =>
  useMutation({
    mutationFn: (body: { data: CardData; services: CardServiceIn[] }) =>
      http<CardSaved>(`${I}/${id}/save`, { method: 'POST', body: JSON.stringify(body) }),
  });

export const useCard = (id: string | undefined) =>
  useQuery({ queryKey: ['card', id], queryFn: () => http<CardView>(`${I}/${id}`), enabled: !!id });
