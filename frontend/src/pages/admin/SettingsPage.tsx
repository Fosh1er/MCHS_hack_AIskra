/** Настройки и резервные копии (п. 5.2): тайминг и пороги занятия по умолчанию, хранение копий, модели ИИ
 *  (просмотр — правятся в config/ai.yaml), создание, скачивание и восстановление копии. */
import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Banner, Button, Card } from '@smena112/ui-kit';
import { useAIConfig } from '../../shared/api/system';
import { http } from '../../shared/api/http';
import { backupUrl, restoreBackup, useBackups, useCreateBackup, useLimits, useSaveSettings, useSettings } from '../../shared/api/admin';
import { CabinetShell } from '../../shared/ui/CabinetShell';
import { bytes } from '../../shared/format';

const LABELS: Record<string, string> = {
  norm_112: 'Норматив карточки 112, с', norm_dds: 'Норматив решения ДДС, с', threshold: 'Порог «зачтено», балл',
  difficulty: 'Сложность вызовов, 1–5', call_interval_s: 'Темп вызовов 112, с', feed_interval_s: 'Темп карточек ДДС, с',
  max_waiting: 'Очередь ДДС, не больше', keep: 'Хранить копий', call_stream: 'Поток учебных вызовов 112: 1 — работает, 0 — остановлен', dds_feed: 'Выдача карточек в очередь ДДС: 1 — работает, 0 — остановлена', auto: 'Ежедневная копия: 1 — включена, 0 — нет', daily_hour: 'Час ежедневной копии (МСК, 0–23)', retention_days: 'Срок хранения журнала аудита, дней (от 183)',
};
const TITLES: Record<string, string> = { session_defaults: 'Занятие по умолчанию', backup: 'Хранение копий', services: 'Сервисы тренажёра: запуск и остановка', audit: 'Журнал аудита' };
const size = bytes;

function Section({ k, values }: { k: string; values: Record<string, number> }) {
  const limits = useLimits().data?.[k] ?? {};
  const save = useSaveSettings();
  const [f, setF] = useState(values);
  useEffect(() => setF(values), [values]);
  const dirty = Object.keys(f).some((x) => f[x] !== values[x]);
  return (
    <Card title={TITLES[k] ?? k} subtitle={k === 'session_defaults' ? 'Подставляются в новое занятие; преподаватель может изменить' : undefined}>
      <div className="tch-form tch-form--grid">
        {Object.keys(values).map((x) => (
          <label key={x}>{LABELS[x] ?? x}
            <input type="number" min={limits[x]?.[1]} max={limits[x]?.[2]} value={f[x]} onChange={(e) => setF({ ...f, [x]: Number(e.target.value) })} />
          </label>
        ))}
      </div>
      <div className="cab-filters" style={{ marginTop: 10 }}>
        <Button variant="primary" icon="save" disabled={!dirty || save.isPending} onClick={() => save.mutate({ key: k, values: f })}>сохранить</Button>
        {dirty && <Button variant="ghost" onClick={() => setF(values)}>отменить</Button>}
        {save.isSuccess && !dirty && <span className="cab-filters__label">сохранено, изменение в аудите</span>}
      </div>
      {save.isError && <Banner status="critical">{save.error.message}</Banner>}
    </Card>
  );
}

function AuditPurge() {
  const [result, setResult] = useState<{ deleted: number; before: string; dry_run: boolean } | null>(null);
  const [error, setError] = useState('');
  const run = async (dry: boolean) => {
    setError('');
    try { setResult(await http<{ deleted: number; before: string; dry_run: boolean }>(`/api/v1/audit/purge?dry_run=${dry}`, { method: 'POST' })); }
    catch (e) { setError((e as Error).message); }
  };
  return (
    <Card title="Очистка журнала аудита" subtitle="Удаляются только записи старше срока хранения — не моложе 6 месяцев (ТЗ). Очистка пишется в аудит.">
      <div className="cab-filters">
        <Button onClick={() => { void run(true); }}>сколько будет удалено</Button>
        <Button variant="danger" onClick={() => { if (window.confirm('Удалить записи журнала старше срока хранения?')) void run(false); }}>очистить</Button>
        {result && <span className="cab-filters__label">записей старше {new Date(result.before).toLocaleDateString('ru-RU')}: {result.deleted}{result.dry_run ? ' (проверка)' : ' — удалено'}</span>}
      </div>
      {error && <Banner status="critical">{error}</Banner>}
    </Card>
  );
}

function Backups() {
  const list = useBackups();
  const create = useCreateBackup();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [restoring, setRestoring] = useState<string | null>(null);
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const restore = async () => {
    setError('');
    try {
      await restoreBackup(restoring!, confirm);
      qc.clear();
      navigate('/', { replace: true }); // все сессии завершены — вход заново
    } catch (e) { setError((e as Error).message); }
  };
  return (
    <Card title="Резервные копии" subtitle="Рабочие данные: пользователи, группы, сценарии, занятия, карточки, оценки, аудит, настройки. Справочники — импортом."
      actions={<Button variant="primary" icon="save" disabled={create.isPending} onClick={() => create.mutate()}>{create.isPending ? 'создаю…' : 'создать копию'}</Button>}>
      {create.data && <Banner>Копия {create.data.name}: таблиц {create.data.tables}, строк {create.data.rows}.</Banner>}
      {create.isError && <Banner status="critical">{create.error.message}</Banner>}
      <table className="cab-table">
        <thead><tr><th>Копия</th><th>Создана</th><th className="num">Размер</th><th /></tr></thead>
        <tbody>
          {list.data?.map((b) => (
            <tr key={b.name}>
              <td>{b.name}</td><td>{new Date(b.created_at).toLocaleString('ru-RU')}</td><td className="num">{size(b.size_bytes)}</td>
              <td className="cab-filters">
                <a className="cab-btn cab-btn--sm" href={backupUrl(b.name)} download>скачать</a>
                <Button size="sm" variant="ghost" onClick={() => { setRestoring(b.name); setConfirm(''); }}>восстановить</Button>
              </td>
            </tr>
          ))}
          {list.data && !list.data.length && <tr><td colSpan={4} className="c-slate">Копий пока нет.</td></tr>}
        </tbody>
      </table>
      {restoring && (
        <div className="tch-override" style={{ maxWidth: 640 }}>
          <Banner status="critical">Восстановление из {restoring} заменит все рабочие данные состоянием копии, всё созданное после неё пропадёт. Все пользователи выйдут из системы.</Banner>
          <div className="tch-form" style={{ marginTop: 8 }}>
            <label>Для подтверждения введите «ВОССТАНОВИТЬ»<input value={confirm} onChange={(e) => setConfirm(e.target.value)} /></label>
          </div>
          <div className="cab-filters" style={{ marginTop: 8 }}>
            <Button variant="danger" disabled={confirm !== 'ВОССТАНОВИТЬ'} onClick={() => { void restore(); }}>восстановить</Button>
            <Button variant="ghost" onClick={() => setRestoring(null)}>отмена</Button>
          </div>
          {error && <Banner status="critical">{error}</Banner>}
        </div>
      )}
    </Card>
  );
}

function AiModels() {
  const ai = useAIConfig();
  return (
    <Card title="Модели ИИ" subtitle="Эндпоинты и ключи — в config/ai.yaml и .env (не хранятся в БД); проверка — «ИИ-модели»" flush>
      <table className="cab-table">
        <thead><tr><th>Задача</th><th>Провайдер</th><th>Модель</th></tr></thead>
        <tbody>
          {ai.data?.tasks.map((t) => <tr key={t.task}><td>{t.task}</td><td>{t.provider}</td><td>{t.model}</td></tr>)}
          {ai.data && !ai.data.tasks.length && <tr><td colSpan={3} className="c-slate">Задачи не настроены — работает офлайн-режим ({ai.data.default_provider}).</td></tr>}
        </tbody>
      </table>
    </Card>
  );
}

export function SettingsPage() {
  const s = useSettings();
  return (
    <CabinetShell kind="admin" active="settings" title="Настройки и резервные копии">
      {s.isError && <Banner status="critical">{s.error.message}</Banner>}
      {s.data && Object.entries(s.data).map(([k, v]) => <Section key={k} k={k} values={v} />)}
      <AuditPurge />
      <Backups />
      <AiModels />
    </CabinetShell>
  );
}
