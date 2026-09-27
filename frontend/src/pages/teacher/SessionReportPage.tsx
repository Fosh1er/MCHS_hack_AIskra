/** Отчёт по занятию (п. 4.3). ТЗ, сценарии 2–3: действия, ошибки, время против норматива, грамматика; наглядные
 *  диаграммы; экспертная правка оценки с комментарием; выгрузка в Excel (CSV) и PDF (печать страницы). */
import { Fragment, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Banner, Button, Card, LineChart, StatTile, StatusPill } from '@smena112/ui-kit';
import { reportCsvUrl, useEvaluateSession, useOverride, useSessionReport, type CardResult, type SessionReport } from '../../shared/api/assessment';
import { TeacherShell } from '../../shared/ui/TeacherShell';
import { num } from '../../shared/format';

const pct = (x: number | null) => (x === null ? '—' : `${Math.round(x * 100)} %`);
const heatClass = (v: number | undefined) => (v === undefined ? 'na' : v >= 0.85 ? 'h4' : v >= 0.7 ? 'h3' : v >= 0.5 ? 'h2' : v >= 0.3 ? 'h1' : 'h0');

function OverrideForm({ card, sessionId, threshold, onClose }: { card: CardResult; sessionId: string; threshold: number; onClose: () => void }) {
  const ov = useOverride(sessionId);
  const [score, setScore] = useState(card.score ?? 0);
  const [comment, setComment] = useState('');
  return (
    <div className="tch-form tch-override">
      <label>Балл эксперта<input type="number" min={0} max={100} value={score} onChange={(e) => setScore(Number(e.target.value))} /></label>
      <label>Комментарий обучающемуся (обязательно)<textarea rows={2} value={comment} onChange={(e) => setComment(e.target.value)} /></label>
      <div className="cab-filters">
        <Button size="sm" variant="primary" disabled={ov.isPending || comment.trim().length < 3}
          onClick={() => ov.mutate({ id: card.assessment_id!, score, comment, threshold }, { onSuccess: onClose })}>сохранить оценку</Button>
        <Button size="sm" variant="ghost" onClick={onClose}>отмена</Button>
        <span className="cab-filters__label">{score >= threshold ? 'зачтено' : 'не зачтено'} при пороге {threshold}</span>
      </div>
      {ov.isError && <Banner status="critical">{ov.error.message}</Banner>}
    </div>
  );
}

function StudentsTable({ r }: { r: SessionReport }) {
  const [open, setOpen] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [all, setAll] = useState(false);
  useEffect(() => { // в PDF — все карточки раскрыты
    const on = () => setAll(true);
    window.addEventListener('beforeprint', on);
    return () => window.removeEventListener('beforeprint', on);
  }, []);
  const threshold = r.settings.threshold ?? 70;
  return (
    <Card title="Результаты обучающихся" subtitle="Нажмите строку, чтобы раскрыть карточки" flush
      actions={<Button size="sm" variant="ghost" onClick={() => setAll(!all)}>{all ? 'свернуть все' : 'раскрыть все'}</Button>}>
      <table className="cab-table">
        <thead><tr><th>ФИО</th><th>Роль</th><th className="num">Карточек</th><th className="num">Средний балл</th><th className="num">Зачтено</th><th className="num">Среднее время, с</th><th className="num">Не оценено</th></tr></thead>
        <tbody>
          {r.students.map((s) => (
            <Fragment key={s.student_id}>
              <tr onClick={() => setOpen(open === s.student_id ? null : s.student_id)} style={{ cursor: 'pointer' }} aria-expanded={open === s.student_id}>
                <td><b>{s.full_name}</b></td>
                <td>{s.role === '112' ? 'оператор 112' : `ДДС ${s.service_code}`}</td>
                <td className="num">{s.cards.length}</td>
                <td className="num">{num(s.avg_score)}</td>
                <td className="num">{pct(s.passed_share)}</td>
                <td className="num">{num(s.avg_time_s)}</td>
                <td className="num">{s.not_assessed || ''}</td>
              </tr>
              {(all || open === s.student_id) && s.cards.map((c) => (
                <tr key={c.card_id} className="tch-subrow">
                  <td colSpan={7}>
                    <div className="tch-cardline">
                      <b>№ {c.card_number}</b>
                      <span>{c.card_types.join(', ')}</span>
                      {c.processing_s !== null && (
                        <span className={c.deviation_s !== null && c.deviation_s > 0 ? 'c-red' : ''}>
                          {Math.round(c.processing_s)} с (норматив {c.norm_s}, {c.deviation_s !== null && c.deviation_s > 0 ? '+' : ''}{c.deviation_s})
                        </span>
                      )}
                      {c.score !== null
                        ? <StatusPill status={c.passed ? 'ok' : 'critical'}>{num(c.score)} {c.expert ? '· эксперт' : ''}</StatusPill>
                        : <StatusPill status="neutral">не оценена</StatusPill>}
                      {c.assessment_id && <Button size="sm" variant="ghost" icon="edit" onClick={() => setEditing(editing === c.card_id ? null : c.card_id)}>правка</Button>}
                    </div>
                    {c.expert_comment && <div className="tch-expert">Эксперт: {c.expert_comment}</div>}
                    {c.errors.length > 0 && <ul className="tch-errors">{c.errors.map((e) => <li key={e}>{e}</li>)}</ul>}
                    {editing === c.card_id && <OverrideForm card={c} sessionId={r.session_id} threshold={threshold} onClose={() => setEditing(null)} />}
                  </td>
                </tr>
              ))}
            </Fragment>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function HeatTable({ criteria, rows }: { criteria: { key: string; title: string }[]; rows: SessionReport['heatmap']['rows'] }) {
  return (
    <div className="tch-heat-wrap">
      <table className="tch-heat">
        <thead><tr><th />{criteria.map((c) => <th key={c.key} scope="col"><span>{c.title}</span></th>)}</tr></thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.student + row.role}>
              <th scope="row">{row.student}</th>
              {criteria.map((c) => {
                const v = row.values[c.key];
                return <td key={c.key} className={`tch-heat__${heatClass(v)}`} title={`${row.student} · ${c.title}: ${v === undefined ? 'нет данных' : pct(v)}`}>{v === undefined ? '' : Math.round(v * 100)}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Тепловая карта по ролям: у оператора 112 и диспетчера ДДС разные критерии, в одной таблице они бы не сравнивались. */
function Heatmap({ r }: { r: SessionReport }) {
  const h = r.heatmap;
  const parts = (['112', 'dds'] as const).map((role) => {
    const rows = h.rows.filter((x) => x.role === role);
    const criteria = h.criteria.filter((c) => rows.some((x) => x.values[c.key] !== undefined));
    return { role, rows, criteria };
  }).filter((p) => p.criteria.length);
  if (!parts.length) return null;
  return (
    <Card title="Тепловая карта: обучающийся × критерий" subtitle="Средний балл критерия, 0–100 %; чем темнее, тем лучше">
      <div className="tch-heat-parts">
        {parts.map((p) => (
          <div key={p.role}>
            <div className="cab-filters__label" style={{ marginBottom: 4 }}>{p.role === '112' ? 'Операторы 112' : 'Диспетчеры ДДС'}</div>
            <HeatTable criteria={p.criteria} rows={p.rows} />
          </div>
        ))}
      </div>
    </Card>
  );
}

function TimeHistogram({ r }: { r: SessionReport }) {
  const max = Math.max(1, ...r.time_buckets.map((b) => b.count));
  const norm = r.settings.norm_112 ?? 75;
  return (
    <Card title="Время заполнения карточки 112" subtitle={`Норматив ${norm} с`}>
      <div className="tch-hist" role="img" aria-label={r.time_buckets.map((b) => `${b.label}: ${b.count}`).join(', ')}>
        {r.time_buckets.map((b) => (
          <div key={b.label} className="tch-hist__col">
            <span className="tch-hist__val">{b.count}</span>
            <span className="tch-hist__bar" style={{ height: `${(b.count / max) * 100}%` }} />
            <span className="tch-hist__label">{b.label}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}

export function SessionReportPage() {
  const { id = '' } = useParams();
  const q = useSessionReport(id);
  const evaluate = useEvaluateSession(id);
  const r = q.data;
  return (
    <TeacherShell active="sessions" crumbs="Пульт / Занятия / Отчёт" title={r ? `Отчёт: ${r.title}` : 'Отчёт по занятию'}
      subtitle={r?.started_at ? new Date(r.started_at).toLocaleString('ru-RU') : undefined}
      actions={
        <span className="tch-noprint cab-filters">
          <Button icon="refresh" disabled={evaluate.isPending} onClick={() => evaluate.mutate()}>{evaluate.isPending ? 'оценка…' : 'оценить все карточки'}</Button>
          <Link className="cab-btn" to={`/teacher/sessions/${id}/debrief`}>разбор</Link>
          <a className="cab-btn" href={reportCsvUrl(id)} download>Excel (CSV)</a>
          <Button icon="description" onClick={() => window.print()}>PDF</Button>
        </span>
      }>
      {q.isError && <Banner status="critical">{q.error.message}</Banner>}
      {evaluate.data && <Banner>Оценено карточек: {evaluate.data.assessed}{evaluate.data.skipped ? `, пропущено: ${evaluate.data.skipped} (ДДС не открывала карточку или карточка — черновик)` : ''}.</Banner>}
      {evaluate.isError && <Banner status="critical">{evaluate.error.message}</Banner>}
      {r && (
        <>
          <section className="cab-kpis">
            <StatTile label="Средний балл" value={num(r.avg_score)} note={`порог ${r.settings.threshold}`} />
            <StatTile label="Зачтено" value={pct(r.passed_share)} />
            <StatTile label="Карточек" value={r.cards_count} />
            <StatTile label="Обучающихся" value={r.students.length} />
          </section>
          {r.cards_count > 0 && r.students.every((s) => s.cards.every((c) => c.score === null)) && (
            <Banner>Карточки ещё не оценены — нажмите «оценить все карточки».</Banner>
          )}
          <StudentsTable r={r} />
          <Heatmap r={r} />
          <TimeHistogram r={r} />
          {r.score_series.length >= 2 && (
            <Card title="Динамика баллов по ходу занятия">
              <LineChart points={r.score_series.map((p) => ({ t: new Date(p.t).toLocaleTimeString('ru-RU'), v: p.v }))}
                yMax={100} yStep={20} unit="балл" seriesLabel="Балл за карточку" threshold={{ value: r.settings.threshold ?? 70, label: 'порог' }} />
            </Card>
          )}
        </>
      )}
    </TeacherShell>
  );
}
