/** Диагностика ИИ (эталонный вертикальный срез п. 0.1): запрос конфигурации + команда пробного вызова. */
import { useState } from 'react';
import { Button, Card, StatusPill } from '@smena112/ui-kit';
import { useAIConfig, useHealth, useProbeModel } from '../shared/api/system';

export function AiDiagnosticsPage() {
  const health = useHealth();
  const config = useAIConfig();
  const probe = useProbeModel();
  const [prompt, setPrompt] = useState('Скажи «готов», если слышишь меня');
  const [task, setTask] = useState('probe');

  return (
    <div className="cab-content" style={{ maxWidth: 1100, margin: '0 auto' }}>
      <h1 className="cab-title">Диагностика ИИ-провайдеров</h1>
      <Card title="Состояние">
        {health.data ? (
          <div className="u-row">
            <StatusPill status={health.data.status === 'ok' ? 'ok' : 'warn'}>API: {health.data.status}</StatusPill>
            <StatusPill status={health.data.db === 'ok' ? 'ok' : 'critical'}>БД: {health.data.db}</StatusPill>
            <StatusPill status="info">кеш: {Math.round(health.data.ai.cache.hit_rate * 100)}% попаданий</StatusPill>
          </div>
        ) : (
          <StatusPill status="neutral">{health.isError ? 'бэкенд недоступен' : 'загрузка…'}</StatusPill>
        )}
      </Card>
      <Card title="Назначение моделей на задачи" subtitle={config.data ? `внешние адреса: ${config.data.allow_external ? 'разрешены' : 'запрещены'}` : undefined} flush>
        <table className="cab-table">
          <thead><tr><th>Задача</th><th>Провайдер</th><th>Модель</th><th className="num">t°</th><th>Кеш</th></tr></thead>
          <tbody>
            {config.data?.tasks.map((t) => (
              <tr key={t.task}><td>{t.task}</td><td>{t.provider}</td><td>{t.model}</td><td className="num">{t.temperature}</td><td>{t.cache_mode}</td></tr>
            ))}
          </tbody>
        </table>
      </Card>
      <Card title="Пробный вызов (команда)">
        <div className="u-row" style={{ alignItems: 'stretch' }}>
          <select className="cab-select" value={task} onChange={(e) => setTask(e.target.value)} aria-label="Задача">
            {(config.data?.tasks ?? []).map((t) => <option key={t.task}>{t.task}</option>)}
          </select>
          <input className="cab-select u-grow" value={prompt} onChange={(e) => setPrompt(e.target.value)} aria-label="Запрос" />
          <Button variant="primary" icon="send" disabled={probe.isPending} onClick={() => probe.mutate({ prompt, task })}>Отправить</Button>
        </div>
        {probe.data && (
          <p style={{ marginTop: 12 }}>
            <StatusPill status={probe.data.cached ? 'ok' : 'info'}>{probe.data.cached ? 'из кеша' : 'от модели'} · {probe.data.latency_ms} мс</StatusPill>{' '}
            {probe.data.provider}/{probe.data.model}: {probe.data.text}
          </p>
        )}
        {probe.error && <p style={{ marginTop: 12 }}><StatusPill status="critical">{probe.error.message}</StatusPill></p>}
      </Card>
    </div>
  );
}
