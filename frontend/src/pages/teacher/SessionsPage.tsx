/** Занятия (п. 4.2): список и создание. ТЗ, сценарии 2–3: тип занятия, категории событий, источник карточек,
 *  обучающиеся и их роли (оператор 112 или диспетчер конкретной ДДС), нормативы и темп. */
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Banner, Button, Card, StatusPill } from '@smena112/ui-kit';
import { useIncidentGroups, useServices } from '../../shared/api/dictionaries';
import {
  MODE_TITLE, SESSION_STATUS, SOURCE_TITLE, useCreateSession, useSessions, useStudents,
  type CardSource, type CreateSessionBody, type SessionMode, type SessionSettings,
} from '../../shared/api/training';
import { TeacherShell } from '../../shared/ui/TeacherShell';
import { GroupPicker } from './ScenariosPage';

const DEFAULTS: SessionSettings = { norm_112: 80, norm_dds: 30, threshold: 70, difficulty: 2, call_interval_s: 40, feed_interval_s: 45, max_waiting: 3 };
const SETTING_LABELS: [keyof SessionSettings, string, number, number][] = [
  ['norm_112', 'Норматив карточки 112, с', 5, 3600],
  ['norm_dds', 'Норматив решения ДДС, с', 5, 3600],
  ['threshold', 'Порог «зачтено», балл', 0, 100],
  ['difficulty', 'Сложность вызовов, 1–5', 1, 5],
  ['call_interval_s', 'Темп вызовов 112, с', 5, 3600],
  ['feed_interval_s', 'Темп карточек ДДС, с', 5, 3600],
  ['max_waiting', 'Очередь ДДС, не больше', 1, 10],
];
type Role = '' | '112' | 'dds';

function CreateForm({ onCreated }: { onCreated: (id: string) => void }) {
  const students = useStudents();
  const groups = useIncidentGroups();
  const services = useServices();
  const create = useCreateSession();
  // экстренные службы — первыми: с ними чаще всего тренируют ДДС (п. 2.1)
  const dds = useMemo(() => [...(services.data ?? [])].sort((a, b) => Number(b.kind === 'emergency') - Number(a.kind === 'emergency')), [services.data]);
  const [title, setTitle] = useState('');
  const [mode, setMode] = useState<SessionMode>('mixed');
  const [source, setSource] = useState<CardSource>('generated');
  const [picked, setPicked] = useState<number[]>([]);
  const [roles, setRoles] = useState<Record<string, { role: Role; service: string }>>({});
  const [settings, setSettings] = useState<SessionSettings>(DEFAULTS);
  const setRole = (id: string, patch: Partial<{ role: Role; service: string }>) =>
    setRoles((r) => ({ ...r, [id]: { ...(r[id] ?? { role: '', service: '' }), ...patch } }));
  const participants = Object.entries(roles).filter(([, v]) => v.role).map(([id, v]) => ({
    student_id: id, role: v.role as '112' | 'dds', dds_service_code: v.role === 'dds' ? v.service || null : null,
  }));
  const missingService = participants.some((p) => p.role === 'dds' && !p.dds_service_code);
  const submit = () => {
    const body: CreateSessionBody = { title: title.trim(), mode, card_source: source, groups: picked, participants, settings };
    create.mutate(body, { onSuccess: (r) => onCreated(r.id) });
  };
  return (
    <Card title="Новое занятие">
      <div className="tch-form tch-form--grid">
        <label>Название<input value={title} placeholder="Например: пожары в жилом секторе" onChange={(e) => setTitle(e.target.value)} /></label>
        <label>Тип занятия
          <select value={mode} onChange={(e) => setMode(e.target.value as SessionMode)}>
            {(Object.keys(MODE_TITLE) as SessionMode[]).map((m) => <option key={m} value={m}>{MODE_TITLE[m]}</option>)}
          </select>
        </label>
        <label>Карточки для ДДС
          <select value={source} onChange={(e) => setSource(e.target.value as CardSource)}>
            {(Object.keys(SOURCE_TITLE) as CardSource[]).map((m) => <option key={m} value={m}>{SOURCE_TITLE[m]}</option>)}
          </select>
        </label>
      </div>
      <GroupPicker groups={groups.data ?? []} value={picked} onChange={setPicked} />
      <table className="cab-table" style={{ marginTop: 8 }}>
        <thead><tr><th>Обучающийся</th><th>Логин</th><th>Роль на занятии</th><th>Служба (для ДДС)</th></tr></thead>
        <tbody>
          {students.data?.map((s) => {
            const r = roles[s.id] ?? { role: '', service: '' };
            return (
              <tr key={s.id}>
                <td>{s.full_name}</td>
                <td className="c-slate">{s.login}</td>
                <td>
                  <select className="cab-select" aria-label={`Роль: ${s.full_name}`} value={r.role} onChange={(e) => setRole(s.id, { role: e.target.value as Role })}>
                    <option value="">не участвует</option><option value="112">оператор 112</option><option value="dds">диспетчер ДДС</option>
                  </select>
                </td>
                <td>
                  {r.role === 'dds' && (
                    <select className="cab-select" aria-label={`Служба: ${s.full_name}`} value={r.service} onChange={(e) => setRole(s.id, { service: e.target.value })}>
                      <option value="">выберите службу</option>
                      {dds.map((d) => <option key={d.code} value={d.code}>{d.short}</option>)}
                    </select>
                  )}
                </td>
              </tr>
            );
          })}
          {students.data && !students.data.length && <tr><td colSpan={4} className="c-slate">Обучающихся нет — администратор заводит их в разделе пользователей.</td></tr>}
        </tbody>
      </table>
      <div className="tch-form tch-form--grid" style={{ marginTop: 12 }}>
        {SETTING_LABELS.map(([k, label, min, max]) => (
          <label key={k}>{label}
            <input type="number" min={min} max={max} value={settings[k]} onChange={(e) => setSettings({ ...settings, [k]: Number(e.target.value) })} />
          </label>
        ))}
      </div>
      <div className="cab-filters" style={{ marginTop: 12 }}>
        <Button variant="primary" icon="plus" onClick={submit} disabled={create.isPending || title.trim().length < 3 || !participants.length || missingService}>
          создать занятие
        </Button>
        <span className="cab-filters__label">
          {participants.length ? `участников: ${participants.length}` : 'назначьте роли обучающимся'}{missingService ? ' · укажите службу для ДДС' : ''}
        </span>
      </div>
      {create.isError && <Banner status="critical">{create.error.message}</Banner>}
    </Card>
  );
}

export function SessionsPage() {
  const navigate = useNavigate();
  const sessions = useSessions();
  const [creating, setCreating] = useState(false);
  return (
    <TeacherShell active="sessions" crumbs="Пульт / Занятия" title="Занятия"
      actions={!creating && <Button variant="primary" icon="plus" onClick={() => setCreating(true)}>новое занятие</Button>}>
      {creating && <CreateForm onCreated={(id) => navigate(`/teacher/sessions/${id}`)} />}
      <Card flush>
        <table className="cab-table">
          <thead><tr><th>Занятие</th><th>Тип</th><th className="num">Участников</th><th>Начало</th><th>Статус</th><th /></tr></thead>
          <tbody>
            {sessions.data?.items.map((s) => (
              <tr key={s.id}>
                <td><a href={`/teacher/sessions/${s.id}`} onClick={(e) => { e.preventDefault(); navigate(`/teacher/sessions/${s.id}`); }}>{s.title}</a></td>
                <td>{MODE_TITLE[s.mode]}</td>
                <td className="num">{s.participants.length}</td>
                <td>{s.started_at ? new Date(s.started_at).toLocaleString('ru-RU') : '—'}</td>
                <td><StatusPill status={s.status === 'running' ? 'ok' : s.status === 'planned' ? 'info' : 'neutral'}>{SESSION_STATUS[s.status]}</StatusPill></td>
                <td>{s.status !== 'planned' && <Button size="sm" variant="ghost" icon="bar_chart" onClick={() => navigate(`/teacher/sessions/${s.id}/report`)}>отчёт</Button>}</td>
              </tr>
            ))}
            {sessions.data && !sessions.data.total && <tr><td colSpan={6} className="c-slate">Занятий пока нет.</td></tr>}
          </tbody>
        </table>
      </Card>
    </TeacherShell>
  );
}
