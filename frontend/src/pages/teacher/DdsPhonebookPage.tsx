/** Телефоны ДДС (п. 2.3, рекомендация экспертов): преподаватель задаёт абонентов IP-телефона диспетчера службы —
 *  должность, ФИО (синтетическое), условный номер; не больше 10 на службу. «Заявитель» — номер берётся из карточки:
 *  без этой строки диспетчер заявителю не звонит. Пустая книга — телефон ДДС работает как раньше. */
import { useEffect, useMemo, useState } from 'react';
import { Banner, Button, Card } from '@smena112/ui-kit';
import { useServices } from '../../shared/api/dictionaries';
import { usePhonebook, useSavePhonebook, type ContactRole, type PhonebookEntry } from '../../shared/api/training';
import { CabinetShell } from '../../shared/ui/CabinetShell';

const MAX = 10;
const blank = (): PhonebookEntry => ({ role: 'brigade_chief', name: '', number: '' });

export function DdsPhonebookPage() {
  const services = useServices();
  const sorted = useMemo(() => [...(services.data ?? [])].sort((a, b) => a.short.localeCompare(b.short, 'ru')), [services.data]);
  const [service, setService] = useState('');
  const book = usePhonebook(service || undefined);
  const save = useSavePhonebook(service);
  const [rows, setRows] = useState<PhonebookEntry[]>([]);
  const [saved, setSaved] = useState(false);

  useEffect(() => { if (!service && sorted.length) setService(sorted[0].code); }, [service, sorted]);
  useEffect(() => { setRows(book.data?.entries ?? []); }, [book.data]);
  useEffect(() => { setSaved(false); }, [service]);

  const roles = book.data?.roles ?? [];
  const edit = (i: number, patch: Partial<PhonebookEntry>) => { setSaved(false); setRows((r) => r.map((e, j) => (j === i ? { ...e, ...patch } : e))); };
  const remove = (i: number) => { setSaved(false); setRows((r) => r.filter((_, j) => j !== i)); };
  const submit = () => save.mutate(rows, { onSuccess: () => setSaved(true) });

  return (
    <CabinetShell kind="teacher" active="phonebook" title="Телефоны ДДС"
      subtitle="Абоненты IP-телефона диспетчера: не больше 10 номеров на службу">
      <div className="cab-filters">
        <label className="cab-filters__label">Служба
          <select className="cab-select" aria-label="Служба" value={service} onChange={(e) => setService(e.target.value)}>
            {sorted.map((s) => <option key={s.code} value={s.code}>{s.short} · {s.code}</option>)}
          </select>
        </label>
        <span className="c-slate">{book.data?.configured ? `в книге ${book.data.entries.length}` : 'книга не задана — телефон ДДС как раньше'}</span>
      </div>
      <Card flush title="Телефонная книга" subtitle="«Заявитель» — номер из карточки; без этой строки звонить заявителю нельзя. Номер не из книги — «Номер не обслуживается».">
        <table className="cab-table">
          <thead><tr><th>Должность</th><th>ФИО</th><th>Условный номер</th><th /></tr></thead>
          <tbody>
            {rows.map((e, i) => (
              <tr key={i}>
                <td>
                  <select className="cab-select" aria-label={`Должность, строка ${i + 1}`} value={e.role}
                    onChange={(ev) => edit(i, { role: ev.target.value as ContactRole, ...(ev.target.value === 'applicant' ? { number: '' } : {}) })}>
                    {roles.map((r) => <option key={r.code} value={r.code}>{r.title}</option>)}
                  </select>
                </td>
                <td><input className="cab-select" aria-label={`ФИО, строка ${i + 1}`} value={e.name} maxLength={120}
                  placeholder={e.role === 'applicant' ? 'необязательно' : 'Фамилия Имя Отчество'} onChange={(ev) => edit(i, { name: ev.target.value })} /></td>
                <td>{e.role === 'applicant'
                  ? <span className="c-slate">из карточки</span>
                  : <input className="cab-select" aria-label={`Номер, строка ${i + 1}`} value={e.number} maxLength={24} placeholder="101-10"
                      onChange={(ev) => edit(i, { number: ev.target.value })} />}</td>
                <td><Button size="sm" variant="ghost" icon="close" onClick={() => remove(i)}>убрать</Button></td>
              </tr>
            ))}
            {!rows.length && <tr><td colSpan={4} className="c-slate">Абонентов нет.</td></tr>}
          </tbody>
        </table>
      </Card>
      <div className="cab-filters" style={{ marginTop: 10 }}>
        <Button variant="ghost" icon="plus" disabled={rows.length >= MAX || !service} onClick={() => { setSaved(false); setRows((r) => [...r, blank()]); }}>
          добавить ({rows.length}/{MAX})
        </Button>
        <Button variant="primary" disabled={!service || save.isPending} onClick={submit}>{save.isPending ? 'сохранение…' : 'сохранить'}</Button>
        {saved && <span className="c-slate" role="status">Сохранено</span>}
      </div>
      {save.isError && <Banner status="critical">{save.error.message}</Banner>}
    </CabinetShell>
  );
}
