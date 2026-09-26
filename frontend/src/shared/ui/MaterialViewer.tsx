/** Просмотр материала (п. 4.4): PDF — встроенный просмотрщик браузера, DOCX/XLSX/TXT — извлечённый текст;
 *  найденные по запросу места — вверху, слова запроса подсвечены. */
import { Fragment } from 'react';
import { Card } from '@smena112/ui-kit';
import { KIND_TITLE, fileUrl, useMaterial } from '../api/materials';

function highlight(text: string, q: string) {
  const words = q.toLowerCase().split(/\s+/).filter((w) => w.length >= 3).map((w) => w.slice(0, 5));
  if (!words.length) return text;
  const re = new RegExp(`(${words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'gi');
  return text.split(re).map((part, i) => (i % 2 ? <mark key={i}>{part}</mark> : <Fragment key={i}>{part}</Fragment>));
}

export function MaterialViewer({ id, q }: { id: string; q: string }) {
  const m = useMaterial(id, q).data;
  if (!m) return <Card title="Материал">загрузка…</Card>;
  return (
    <Card title={m.title} subtitle={`${KIND_TITLE[m.kind]} · ${m.filename}`}
      actions={<a className="cab-btn cab-btn--sm" href={fileUrl(m.id, true)} download>скачать</a>}>
      {m.found.length > 0 && (
        <div className="mat-found">
          <b>Найдено по запросу «{q}»</b>
          {m.found.map((p, i) => <p key={i}>{highlight(p, q)}</p>)}
        </div>
      )}
      {m.file_type === 'pdf'
        ? <iframe className="mat-pdf" title={m.title} src={fileUrl(m.id)} />
        : <div className="mat-text">{m.text ? highlight(m.text.slice(0, 200_000), q) : 'Текст не извлечён — скачайте файл.'}</div>}
    </Card>
  );
}
