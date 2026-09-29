/** Банк сценариев (п. 4.1): фильтры, генерация, просмотр легенды и эталона, прогон, правка, перегенерация по
 *  комментарию, утверждение и архив. ТЗ сценарий 1: «сгенерировать → проверить → утвердить или доработать». */
import { useEffect, useState } from 'react';
import { Banner, Button, Card, Segmented, StatusPill, Tag } from '@smena112/ui-kit';
import { useCardTypes, useEnum, useIncidentGroups, useServices } from '../../shared/api/dictionaries';
import {
  useEditScenario, useGenerateScenarios, usePsyProfiles, useReviewScenario, useScenario, useScenarioPreview, useScenarios, useSetScenarioPsy,
  type ScenarioFilter, type ScenarioRow, type ScenarioView,
} from '../../shared/api/training';
import { TeacherShell } from '../../shared/ui/TeacherShell';
import { useScreenTour } from '../../shared/onboarding/OnboardingProvider';

const STATUS: Record<ScenarioRow['status'], { label: string; pill: 'info' | 'ok' | 'neutral' }> = {
  draft: { label: 'на проверке', pill: 'info' },
  approved: { label: 'утверждён', pill: 'ok' },
  archived: { label: 'в архиве', pill: 'neutral' },
};
const SOURCE: Record<string, string> = { ai: 'ИИ', template: 'шаблон' };
const DIFFICULTY = ['', 'очень лёгкий', 'лёгкий', 'средний', 'сложный', 'очень сложный'];

function GenerateForm({ onDone }: { onDone: (n: number) => void }) {
  const groups = useIncidentGroups();
  const gen = useGenerateScenarios();
  const [count, setCount] = useState(5);
  const [difficulty, setDifficulty] = useState(2);
  const [picked, setPicked] = useState<number[]>([]);
  return (
    <Card title="Сгенерировать сценарии" subtitle="Черновики попадут в банк на проверку" tour="t-generate">
      <div className="cab-filters">
        <label className="cab-filters__label">Количество <input className="cab-select" type="number" min={1} max={50} value={count} onChange={(e) => setCount(Number(e.target.value))} style={{ width: 70 }} /></label>
        <label className="cab-filters__label">Сложность{' '}
          <select className="cab-select" value={difficulty} onChange={(e) => setDifficulty(Number(e.target.value))}>
            {[1, 2, 3, 4, 5].map((d) => <option key={d} value={d}>{d} — {DIFFICULTY[d]}</option>)}
          </select>
        </label>
        <Button variant="primary" icon="bolt" disabled={gen.isPending}
          onClick={() => gen.mutate({ count, difficulty, groups: picked }, { onSuccess: (r) => onDone(r.ids.length) })}>
          {gen.isPending ? 'генерация…' : 'сгенерировать'}
        </Button>
      </div>
      <details className="tch-details">
        <summary>категории событий: {picked.length ? `выбрано ${picked.length}` : 'любые'}</summary>
        <GroupPicker groups={groups.data ?? []} value={picked} onChange={setPicked} />
      </details>
      {gen.isError && <Banner status="critical">{gen.error.message}</Banner>}
    </Card>
  );
}

export function GroupPicker({ groups, value, onChange }: { groups: { id: number; title: string }[]; value: number[]; onChange: (v: number[]) => void }) {
  const toggle = (id: number) => onChange(value.includes(id) ? value.filter((x) => x !== id) : [...value, id]);
  return (
    <fieldset className="tch-groups">
      <legend className="cab-filters__label">Категории событий (группы классификатора){value.length ? `: выбрано ${value.length}` : ': любые'}</legend>
      {groups.map((g) => (
        <label key={g.id} className={value.includes(g.id) ? 'is-on' : ''}>
          <input type="checkbox" checked={value.includes(g.id)} onChange={() => toggle(g.id)} /> {g.id}. {g.title}
        </label>
      ))}
    </fieldset>
  );
}

function Legend({ s }: { s: ScenarioView }) {
  const services = useServices();
  const statuses = useEnum('applicant_status');
  const names = new Map((services.data ?? []).map((x) => [x.code, x.short]));
  const statusName = (c: string) => statuses.data?.find((x) => x.code === c)?.name ?? c;
  const lg = s.legend as Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
  const ref = s.reference_card as Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
  const signs = Object.values((ref.questionnaire ?? {})[s.card_type_code] ?? {}) as string[];
  return (
    <dl className="tch-dl">
      <dt>Первая фраза</dt><dd>«{lg.opening}»</dd>
      <dt>Что случилось</dt><dd>{lg.what}</dd>
      {lg.details && <><dt>Подробности</dt><dd>{lg.details}</dd></>}
      <dt>Заявитель</dt><dd>{lg.applicant?.name}, {statusName(lg.applicant?.status)}, {lg.applicant?.phone} · {lg.emotion}</dd>
      <dt>Адрес</dt><dd>{lg.address?.label}{lg.address?.floor ? `, подъезд ${lg.address.entrance}, этаж ${lg.address.floor}, кв. ${lg.address.flat}` : ''}</dd>
      <dt>Пострадавшие</dt><dd>{lg.victims?.has ? `есть, ${lg.victims.count}` : 'нет'}</dd>
      {Object.keys(lg.facts ?? {}).length > 0 && <><dt>Факты</dt><dd>{Object.values(lg.facts).join('; ')}</dd></>}
      <dt>Эталон: тип</dt><dd>{ref.final_type} <small className="c-slate">({ref.incident_types?.join(', ')})</small></dd>
      <dt>Эталон: признаки</dt><dd>{signs.join(' → ')}</dd>
      <dt>Эталон: службы</dt>
      <dd>{(ref.services ?? []).map((x: { code: string; main: boolean }) => <Tag key={x.code} variant={x.main ? 'dark' : 'default'}>{names.get(x.code) ?? x.code}</Tag>)}</dd>
    </dl>
  );
}

function EditForm({ s, onClose }: { s: ScenarioView; onClose: () => void }) {
  const edit = useEditScenario();
  const lg = s.legend as Record<string, string>;
  const [f, setF] = useState({ title: s.title, difficulty: s.difficulty, opening: lg.opening ?? '', what: lg.what ?? '', details: lg.details ?? '' });
  const [comment, setComment] = useState('');
  const save = () => edit.mutate({ id: s.id, ...f, details: f.details || undefined }, { onSuccess: onClose });
  const regen = () => edit.mutate({ id: s.id, comment }, { onSuccess: () => { setComment(''); onClose(); } });
  return (
    <div className="tch-form">
      <label>Название<input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></label>
      <label>Сложность
        <select value={f.difficulty} onChange={(e) => setF({ ...f, difficulty: Number(e.target.value) })}>
          {[1, 2, 3, 4, 5].map((d) => <option key={d} value={d}>{d} — {DIFFICULTY[d]}</option>)}
        </select>
      </label>
      <label>Первая фраза заявителя<textarea rows={2} value={f.opening} onChange={(e) => setF({ ...f, opening: e.target.value })} /></label>
      <label>Что случилось<textarea rows={2} value={f.what} onChange={(e) => setF({ ...f, what: e.target.value })} /></label>
      <label>Подробности<textarea rows={2} value={f.details} onChange={(e) => setF({ ...f, details: e.target.value })} /></label>
      <div className="cab-filters">
        <Button variant="primary" icon="save" onClick={save} disabled={edit.isPending}>сохранить</Button>
        <Button variant="ghost" onClick={onClose}>отмена</Button>
      </div>
      <label>Комментарий для перегенерации моделью
        <textarea rows={2} placeholder="Например: заявитель пожилой, путается в адресе" value={comment} onChange={(e) => setComment(e.target.value)} />
      </label>
      <Button icon="refresh" onClick={regen} disabled={edit.isPending || comment.trim().length < 3}>перегенерировать речь заявителя</Button>
      {edit.isError && <Banner status="critical">{edit.error.message}</Banner>}
      <small className="c-slate">После правки сценарий возвращается на проверку — утвердите его снова.</small>
    </div>
  );
}

/** Психологический профиль заявителя (п. 3.7): модификатор сценария, легенда и эталоны не меняются. */
function PsyPick({ s }: { s: ScenarioView }) {
  const profiles = usePsyProfiles().data ?? [];
  const setPsy = useSetScenarioPsy();
  const current = profiles.find((p) => p.id === s.psy_profile);
  return (
    <div className="tch-form" style={{ marginTop: 10 }}>
      <label>Психологический профиль заявителя
        <select value={s.psy_profile ?? ''} disabled={setPsy.isPending} onChange={(e) => setPsy.mutate({ id: s.id, profile: e.target.value || null })}>
          <option value="">без профиля (по настройкам занятия)</option>
          {profiles.map((p) => <option key={p.id} value={p.id}>{p.title}{p.sensitive ? ' ⚠ тяжёлая тема' : ''}</option>)}
        </select>
      </label>
      {current && (
        <small className="c-slate">
          Старт: {current.speech[String(current.start)]} Работает, если в занятии включён модификатор
          {current.sensitive ? ' и профиль явно разрешён' : ''}. Источники: {current.sources.join(', ')}.
        </small>
      )}
      {setPsy.isError && <Banner status="critical">{setPsy.error.message}</Banner>}
    </div>
  );
}

function Detail({ id }: { id: string }) {
  const q = useScenario(id);
  const review = useReviewScenario();
  const [mode, setMode] = useState<'view' | 'edit' | 'preview'>('view');
  const preview = useScenarioPreview(id, mode === 'preview');
  useEffect(() => setMode('view'), [id]);
  const s = q.data;
  if (!s) return <Card title="Сценарий">{q.isError ? q.error.message : 'загрузка…'}</Card>;
  return (
    <Card title={s.title} subtitle={`${STATUS[s.status].label} · сложность ${s.difficulty} · ${SOURCE[s.source] ?? s.source}`} tour="t-detail"
      actions={<Segmented ariaLabel="Режим" value={mode} onChange={setMode}
        options={[{ value: 'view', label: 'легенда' }, { value: 'preview', label: 'прогон' }, { value: 'edit', label: 'правка' }]} />}>
      {mode === 'view' && <Legend s={s} />}
      {mode === 'view' && <PsyPick s={s} />}
      {mode === 'edit' && <EditForm s={s} onClose={() => setMode('view')} />}
      {mode === 'preview' && (
        <ol className="tch-preview">
          {preview.data?.map((p) => (
            <li key={p.question}>
              <div className="tch-preview__op">Оператор: {p.question}</div>
              <div className="tch-preview__party">Заявитель: {p.answer}</div>
              <div className="tch-preview__ref">В карточку: {p.reference}</div>
            </li>
          ))}
          {preview.isFetching && <li>прогон…</li>}
        </ol>
      )}
      <div className="cab-filters" style={{ marginTop: 12 }}>
        {s.status !== 'approved' && <Button variant="primary" icon="check" disabled={review.isPending} onClick={() => review.mutate({ id, approve: true })}>утвердить</Button>}
        {s.status !== 'archived' && <Button variant="ghost" icon="storage" disabled={review.isPending} onClick={() => review.mutate({ id, approve: false })}>в архив</Button>}
      </div>
      {review.isError && <Banner status="critical">{review.error.message}</Banner>}
    </Card>
  );
}

export function ScenariosPage() {
  const cardTypes = useCardTypes();
  const [f, setF] = useState<ScenarioFilter>({ status: 'draft', page: 1, page_size: 20 });
  const [picked, setPicked] = useState<string | null>(null);
  const [info, setInfo] = useState('');
  const list = useScenarios(f);
  useScreenTour('teacher-scenarios', !!list.data);
  const titles = new Map((cardTypes.data ?? []).map((t) => [t.code, t.title]));
  const total = list.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / f.page_size));
  const set = (patch: Partial<ScenarioFilter>) => setF({ ...f, ...patch, page: patch.page ?? 1 });
  return (
    <TeacherShell active="scenarios" crumbs="Пульт / Банк сценариев" title="Банк сценариев" subtitle={`${total} в выборке`}>
      <GenerateForm onDone={(n) => { setInfo(`Создано черновиков: ${n}`); set({ status: 'draft' }); }} />
      {info && <Banner actions={<Button size="sm" variant="ghost" onClick={() => setInfo('')}>скрыть</Button>}>{info}</Banner>}
      <div className="cab-filters">
        <span data-tour="t-status">
          <Segmented ariaLabel="Статус" value={f.status ?? ''} onChange={(v) => set({ status: v || undefined })}
            options={[{ value: 'draft', label: 'на проверке' }, { value: 'approved', label: 'утверждённые' }, { value: 'archived', label: 'архив' }, { value: '', label: 'все' }]} />
        </span>
        <select className="cab-select" aria-label="Сложность" value={f.difficulty ?? ''} onChange={(e) => set({ difficulty: e.target.value ? Number(e.target.value) : undefined })}>
          <option value="">любая сложность</option>
          {[1, 2, 3, 4, 5].map((d) => <option key={d} value={d}>{d} — {DIFFICULTY[d]}</option>)}
        </select>
        <select className="cab-select" aria-label="Тип карточки" value={f.card_type ?? ''} onChange={(e) => set({ card_type: e.target.value || undefined })}>
          <option value="">любой тип карточки</option>
          {(cardTypes.data ?? []).map((t) => <option key={t.code} value={t.code}>{t.code} {t.title}</option>)}
        </select>
        <select className="cab-select" aria-label="Источник" value={f.source ?? ''} onChange={(e) => set({ source: e.target.value || undefined })}>
          <option value="">любой источник</option><option value="ai">ИИ</option><option value="template">шаблон</option>
        </select>
      </div>
      <div className="cab-grid cab-grid--main-aside">
        <Card flush tour="t-list">
          <table className="cab-table">
            <thead><tr><th>Название</th><th>Тип</th><th className="num">Сложн.</th><th>Источник</th><th>Статус</th></tr></thead>
            <tbody>
              {list.data?.items.map((s) => (
                <tr key={s.id} onClick={() => setPicked(s.id)} className={picked === s.id ? 'is-picked' : ''} style={{ cursor: 'pointer' }}>
                  <td>{s.title}</td>
                  <td>{s.card_type_code ? titles.get(s.card_type_code) ?? s.card_type_code : '—'}</td>
                  <td className="num">{s.difficulty}</td>
                  <td>{SOURCE[s.source] ?? s.source}</td>
                  <td><StatusPill status={STATUS[s.status].pill}>{STATUS[s.status].label}</StatusPill></td>
                </tr>
              ))}
              {list.data && !total && <tr><td colSpan={5} className="c-slate">Сценариев нет — сгенерируйте их выше.</td></tr>}
            </tbody>
          </table>
          {pages > 1 && (
            <div className="cab-filters" style={{ padding: 10 }}>
              <Button size="sm" disabled={f.page <= 1} onClick={() => set({ page: f.page - 1 })}>назад</Button>
              <span className="cab-filters__label">стр. {f.page} из {pages}</span>
              <Button size="sm" disabled={f.page >= pages} onClick={() => set({ page: f.page + 1 })}>вперёд</Button>
            </div>
          )}
        </Card>
        {picked ? <Detail id={picked} /> : <Card title="Сценарий" tour="t-detail">Выберите сценарий в списке, чтобы посмотреть легенду, эталон и прогон.</Card>}
      </div>
    </TeacherShell>
  );
}
