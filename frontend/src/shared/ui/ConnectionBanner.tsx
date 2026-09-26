/** «Нет связи с сервером» (п. 6.1): браузер офлайн или запросы падают по сети. Пропадает сам, когда связь
 *  вернулась; незавершённые запросы TanStack Query повторяет, черновик карточки лежит локально. */
import { useEffect, useState } from 'react';
import { useIsFetching, useIsMutating, useQueryClient } from '@tanstack/react-query';
import { Icon } from '@smena112/ui-kit';
import { isTransient } from '../api/resilience';

export function ConnectionBanner() {
  const qc = useQueryClient();
  const [offline, setOffline] = useState(() => typeof navigator !== 'undefined' && navigator.onLine === false);
  const [failing, setFailing] = useState(false);
  const busy = useIsFetching() + useIsMutating();
  useEffect(() => {
    const on = () => setOffline(false);
    const off = () => setOffline(true);
    window.addEventListener('online', on);
    window.addEventListener('offline', off);
    // последняя ошибка любого запроса — сетевая? успех любого запроса — связь есть
    const unsubQ = qc.getQueryCache().subscribe((e) => {
      if (e.type !== 'updated') return;
      const st = e.query.state;
      if (st.status === 'error' && isTransient(st.error)) setFailing(true);
      if (st.status === 'success' && e.action.type === 'success') setFailing(false);
    });
    const unsubM = qc.getMutationCache().subscribe((e) => {
      if (e.type !== 'updated' || !e.mutation) return;
      const st = e.mutation.state;
      if (st.failureCount > 0 && isTransient(st.failureReason)) setFailing(true);
      if (st.status === 'success') setFailing(false);
    });
    return () => { window.removeEventListener('online', on); window.removeEventListener('offline', off); unsubQ(); unsubM(); };
  }, [qc]);
  if (!offline && !failing) return null;
  return (
    <div className="conn-banner" role="alert">
      <Icon name="warning" size="sm" />
      <span><b>Нет связи с сервером.</b> Работа не потеряна: карточка сохраняется на этом компьютере, отправка повторится автоматически{busy ? ' — повторяем…' : '.'}</span>
    </div>
  );
}
