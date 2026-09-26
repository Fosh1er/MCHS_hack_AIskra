/** Модуль training: учебные звонки (п. 1.4, 2.3) и банк сценариев (п. 3.2). */
import { useQuery } from '@tanstack/react-query';
import { http } from './http';

export interface CallStarted { call_id: string; scenario_id: string | null; aon: string; channel: string }
export interface Replica { speaker: 'party' | 'operator' | 'system'; text: string }
export interface CallMessage { speaker: 'party' | 'operator' | 'system'; text: string; at: string }
export interface CallView {
  id: string; role: string; party: 'applicant' | 'brigade' | 'service'; direction: 'in' | 'out'; status: string; aon: string;
  card_id: string | null; service_code: string | null; target_service: string | null;
  started_at: string; answered_at: string | null; ended_at: string | null; messages: CallMessage[];
}

const T = '/api/v1/training';
const post = <R,>(path: string, body: unknown = {}) => http<R>(`${T}${path}`, { method: 'POST', body: JSON.stringify(body) });

export const startIncomingCall = () => post<CallStarted>('/calls/incoming');
export const answerCall = (id: string, cardId: string | null) => post<Replica | null>(`/calls/${id}/answer`, { card_id: cardId });
export const sendReplica = (id: string, text: string) => post<Replica>(`/calls/${id}/replicas`, { text });
export const endCall = (id: string) => post<{ status: string }>(`/calls/${id}/end`);
export const startDdsCall = (b: { card_id: string; service_code: string; party: CallView['party']; target_service?: string | null; incoming?: boolean }) =>
  post<CallStarted>('/calls/dds', b);
export const getCall = (id: string) => http<CallView>(`${T}/calls/${id}`);

export const useCardCalls = (cardId: string | undefined) =>
  useQuery({ queryKey: ['card-calls', cardId], queryFn: () => http<CallView[]>(`${T}/cards/${cardId}/calls`), enabled: !!cardId });
