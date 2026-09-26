/** Логи приложения (п. 5.2): последние записи процесса с фильтром уровня и поиском; обновление каждые 10 с. */
import { useState } from 'react';
import { Banner, Card, Segmented } from '@smena112/ui-kit';
import { useLogs } from '../../shared/api/admin';
import { CabinetShell } from '../../shared/ui/CabinetShell';

export function LogsPage() {
  const [level, setLevel] = useState('INFO');
  const [q, setQ] = useState('');
  const logs = useLogs(level, q);
  return (
    <CabinetShell kind="admin" active="logs" title="Логи" subtitle="последние записи процесса">
      <div className="cab-filters">
        <Segmented ariaLabel="Уровень" value={level} onChange={setLevel}
          options={[{ value: 'INFO', label: 'все' }, { value: 'WARNING', label: 'предупреждения' }, { value: 'ERROR', label: 'ошибки' }]} />
        <input className="cab-select" style={{ width: 260 }} placeholder="поиск по тексту" aria-label="Поиск" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {logs.isError && <Banner status="critical">{logs.error.message}</Banner>}
      <Card flush>
        <table className="cab-table adm-logs">
          <thead><tr><th>Время</th><th>Уровень</th><th>Источник</th><th>Сообщение</th></tr></thead>
          <tbody>
            {logs.data?.map((r, i) => (
              <tr key={i} className={`adm-log--${r.level.toLowerCase()}`}>
                <td>{new Date(r.at).toLocaleTimeString('ru-RU')}</td><td>{r.level}</td><td className="c-slate">{r.logger}</td><td>{r.message}</td>
              </tr>
            ))}
            {logs.data && !logs.data.length && <tr><td colSpan={4} className="c-slate">Записей нет.</td></tr>}
          </tbody>
        </table>
      </Card>
    </CabinetShell>
  );
}
