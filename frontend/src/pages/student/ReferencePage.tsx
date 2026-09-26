/** Справочная база (п. 5.1): классификатор происшествий с поиском по признакам и подсказками оператору,
 *  справочник служб и ДДС. Загрузка учебных материалов (PDF, DOCX) — п. 4.4. */
import { useState } from 'react';
import { Card, Segmented, Tag } from '@smena112/ui-kit';
import { useIncidentGroups, useIncidentTypeSearch, useServices } from '../../shared/api/dictionaries';
import { CabinetShell } from '../../shared/ui/CabinetShell';

function Classifier() {
  const groups = useIncidentGroups();
  const services = useServices();
  const names = new Map((services.data ?? []).map((s) => [s.code, s.short]));
  const [q, setQ] = useState('');
  const [group, setGroup] = useState<number | null>(null);
  const r = useIncidentTypeSearch(q, group);
  return (
    <>
      <div className="cab-filters">
        <input className="cab-select" style={{ width: 320 }} placeholder="поиск: пожар, дым, ДТП, газ…" aria-label="Поиск по классификатору" value={q} onChange={(e) => setQ(e.target.value)} />
        <select className="cab-select" aria-label="Группа" value={group ?? ''} onChange={(e) => setGroup(e.target.value ? Number(e.target.value) : null)}>
          <option value="">все группы</option>
          {groups.data?.map((g) => <option key={g.id} value={g.id}>{g.id}. {g.title}</option>)}
        </select>
        <span className="cab-filters__label">найдено: {r.data?.total ?? 0}</span>
      </div>
      <Card flush>
        <table className="cab-table">
          <thead><tr><th>Код</th><th>Признаки</th><th>Конечный тип</th><th>Типы служб</th></tr></thead>
          <tbody>
            {r.data?.items.map((t) => (
              <tr key={t.code}>
                <td className="c-slate">{t.code}</td>
                <td>{[t.sign1, t.sign2, t.sign3].filter(Boolean).join(' → ')}{t.operator_hint && <div className="stu-hint">Оператору: {t.operator_hint}</div>}</td>
                <td>{t.final_type}</td>
                <td>{t.main_services.map((s) => <Tag key={s}>{names.get(s) ?? s}</Tag>)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </>
  );
}

function Services() {
  const services = useServices();
  const [q, setQ] = useState('');
  const t = q.trim().toLowerCase();
  const list = (services.data ?? []).filter((s) => !t || `${s.short} ${s.full}`.toLowerCase().includes(t)).slice(0, 100);
  return (
    <>
      <div className="cab-filters">
        <input className="cab-select" style={{ width: 320 }} placeholder="служба или ДДС" aria-label="Поиск службы" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <Card flush>
        <table className="cab-table">
          <thead><tr><th>Служба</th><th>Полное название</th><th>Телефон</th></tr></thead>
          <tbody>{list.map((s) => <tr key={s.code}><td><b>{s.short}</b></td><td>{s.full}</td><td>{s.phone}</td></tr>)}</tbody>
        </table>
      </Card>
    </>
  );
}

export function ReferencePage() {
  const [tab, setTab] = useState<'classifier' | 'services'>('classifier');
  return (
    <CabinetShell kind="student" active="reference" title="Справочная база"
      actions={<Segmented ariaLabel="Раздел" value={tab} onChange={setTab} options={[{ value: 'classifier', label: 'классификатор' }, { value: 'services', label: 'службы' }]} />}>
      {tab === 'classifier' ? <Classifier /> : <Services />}
    </CabinetShell>
  );
}
