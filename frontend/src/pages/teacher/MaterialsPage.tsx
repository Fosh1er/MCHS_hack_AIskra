/** Учебные материалы (п. 4.4): загрузка PDF/DOCX/XLSX/TXT, публикация обучающимся, признак «использовать в
 *  генерации сценариев», просмотр, правка и удаление. Преподавателю и администратору. */
import { useState } from 'react';
import { Banner, Button, Card, Tag } from '@smena112/ui-kit';
import { useMe } from '../../shared/api/auth';
import { KIND_TITLE, useDeleteMaterial, useMaterials, useUpdateMaterial, useUploadMaterial, type MaterialKind } from '../../shared/api/materials';
import { CabinetShell } from '../../shared/ui/CabinetShell';
import { MaterialViewer } from '../../shared/ui/MaterialViewer';
import { bytes } from '../../shared/format';

const KINDS = Object.keys(KIND_TITLE) as MaterialKind[];
const size = bytes;

function UploadForm() {
  const up = useUploadMaterial();
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [kind, setKind] = useState<MaterialKind>('instruction');
  const [visible, setVisible] = useState(true);
  const [prompts, setPrompts] = useState(false);
  const [key, setKey] = useState(0);
  const pick = (f: File | null) => { setFile(f); if (f && !title) setTitle(f.name.replace(/\.[^.]+$/, '').replace(/_/g, ' ')); };
  const submit = () => file && up.mutate({ file, title: title.trim(), kind, visible, use_in_prompts: prompts }, {
    onSuccess: () => { setFile(null); setTitle(''); setKey((k) => k + 1); },
  });
  return (
    <Card title="Загрузить материал" subtitle="PDF, DOCX, XLSX, TXT или MD, до 25 МБ. Текст извлекается для поиска и генерации сценариев.">
      <div className="tch-form tch-form--grid">
        <label>Файл<input key={key} type="file" accept=".pdf,.docx,.xlsx,.txt,.md" onChange={(e) => pick(e.target.files?.[0] ?? null)} /></label>
        <label>Название<input value={title} onChange={(e) => setTitle(e.target.value)} /></label>
        <label>Вид<select value={kind} onChange={(e) => setKind(e.target.value as MaterialKind)}>{KINDS.map((k) => <option key={k} value={k}>{KIND_TITLE[k]}</option>)}</select></label>
      </div>
      <div className="cab-filters" style={{ marginTop: 10 }}>
        <label className="cab-filters__label"><input type="checkbox" checked={visible} onChange={(e) => setVisible(e.target.checked)} /> видно обучающимся</label>
        <label className="cab-filters__label"><input type="checkbox" checked={prompts} onChange={(e) => setPrompts(e.target.checked)} /> использовать в генерации сценариев</label>
        <Button variant="primary" icon="plus" disabled={!file || title.trim().length < 3 || up.isPending} onClick={submit}>{up.isPending ? 'загрузка…' : 'загрузить'}</Button>
      </div>
      {up.isError && <Banner status="critical">{up.error.message}</Banner>}
    </Card>
  );
}

export function MaterialsPage() {
  const me = useMe().data!;
  const [q, setQ] = useState('');
  const [open, setOpen] = useState<string | null>(null);
  const list = useMaterials(q);
  const update = useUpdateMaterial();
  const del = useDeleteMaterial();
  return (
    <CabinetShell kind={me.role === 'admin' ? 'admin' : 'teacher'} active="materials" title="Учебные материалы"
      subtitle={`${list.data?.length ?? 0} файлов`}>
      <UploadForm />
      <div className="cab-filters">
        <input className="cab-select" style={{ width: 320 }} placeholder="поиск по названию и тексту" aria-label="Поиск" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {(update.error ?? del.error) && <Banner status="critical">{(update.error ?? del.error)!.message}</Banner>}
      <Card flush>
        <table className="cab-table">
          <thead><tr><th>Материал</th><th>Вид</th><th className="num">Размер</th><th>Обучающимся</th><th>В генерации</th><th /></tr></thead>
          <tbody>
            {list.data?.map((m) => (
              <tr key={m.id} className={open === m.id ? 'is-picked' : ''}>
                <td style={{ cursor: 'pointer' }} onClick={() => setOpen(open === m.id ? null : m.id)}>
                  <b>{m.title}</b><br /><small className="c-slate">{m.filename} · текст {m.text_chars.toLocaleString('ru-RU')} симв.{m.uploaded_by_name ? ` · ${m.uploaded_by_name}` : ''}</small>
                </td>
                <td><Tag>{KIND_TITLE[m.kind]}</Tag></td>
                <td className="num">{size(m.size_bytes)}</td>
                <td><input type="checkbox" aria-label={`Видно обучающимся: ${m.title}`} checked={m.visible} onChange={(e) => update.mutate({ id: m.id, visible: e.target.checked })} /></td>
                <td><input type="checkbox" aria-label={`В генерации: ${m.title}`} checked={m.use_in_prompts} onChange={(e) => update.mutate({ id: m.id, use_in_prompts: e.target.checked })} /></td>
                <td><Button size="sm" variant="ghost" icon="close" onClick={() => { if (window.confirm(`Удалить «${m.title}»?`)) del.mutate(m.id); }}>удалить</Button></td>
              </tr>
            ))}
            {list.data && !list.data.length && <tr><td colSpan={6} className="c-slate">{q ? 'Ничего не найдено.' : 'Материалов пока нет.'}</td></tr>}
          </tbody>
        </table>
      </Card>
      {open && <MaterialViewer id={open} q={q} />}
    </CabinetShell>
  );
}
