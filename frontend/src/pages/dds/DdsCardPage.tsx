/** Карточка в АРМ ДДС (п. 2.2): содержимое от 112 только для чтения (#739), своя служба — статусы через карандаш.
 *  Первое открытие ставит «Получена службой» (dds/image10). Службы в карточке ДДС не добавляются (#701). */
import { useEffect, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useMe } from '../../shared/api/auth';
import { setDdsTimerPaused, useDdsActions, useDdsCard } from '../../shared/api/incidents';
import { useScreenTour, useTourPause } from '../../shared/onboarding/OnboardingProvider';
import { CardViewer } from '../card112/CardViewer';
import { DdsSoftphone } from './DdsSoftphone';

export function DdsCardPage() {
  const { service = '', id = '' } = useParams();
  const me = useMe().data!;
  const navigate = useNavigate();
  const card = useDdsCard(service, id);
  useScreenTour('dds-card', !!card.data);
  // п. 5.3: пока новичок впервые читает подсказки карточки, таймер решения своей службы стоит
  const qc = useQueryClient();
  const deciding = card.data?.next_statuses.includes('accepted') ?? false;
  useTourPause('dds-card', deciding, {
    set: (paused) => setDdsTimerPaused(service, paused, id),
    onSynced: () => { void qc.invalidateQueries({ queryKey: ['dds-journal', service] }); },
  });
  const actions = useDdsActions(service, id);
  const marked = useRef(false);
  const canAct = (card.data?.next_statuses.length ?? 0) > 0 || card.data?.service_status !== 'added';
  useEffect(() => {
    if (marked.current || !card.data || card.data.service_status !== 'added' || !canAct) return;
    marked.current = true;
    actions.received.mutate();
  }, [card.data, actions.received, canAct]);

  if (card.isPending) return <div className="arm112" />;
  if (card.isError) return <div className="arm112"><p className="arm-empty" style={{ padding: 24 }}>{card.error.message}</p></div>;
  const canCall = card.data.next_statuses.length > 0 || !['added', 'received', 'rejected'].includes(card.data.service_status);
  return (
    <>
    {canCall && <DdsSoftphone card={card.data.card} service={service} status={card.data.service_status} />}
    <CardViewer
      key={card.data.card.id}
      view={card.data.card}
      me={me}
      dds={{
        service,
        next: card.data.next_statuses,
        busy: actions.status.isPending,
        onStatus: (b) => actions.status.mutateAsync(b),
        onClose: () => navigate(`/arm/dds/${encodeURIComponent(service)}`),
      }}
    />
    </>
  );
}
