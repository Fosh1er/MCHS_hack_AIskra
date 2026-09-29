/** Мониторинг занятия (п. 4.2): плитка на каждого обучающегося — текущая карточка, таймер против норматива,
 *  очередь ДДС, средний балл, ошибки; старт и завершение. ТЗ: «отслеживание в реальном времени» — опрос каждые 5 с. */
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Banner, Button, Card, StatTile, StatusPill, StudentTile, normStatus, type TileState } from '@smena112/ui-kit';
import { useIncidentGroups, useServices } from '../../shared/api/dictionaries';
import { MODE_TITLE, SESSION_STATUS, SOURCE_TITLE, useMonitor, useSessionState, type MonitorView } from '../../shared/api/training';
import { TeacherShell, initials } from '../../shared/ui/TeacherShell';

const pad = (n: number) => String(n).padStart(2, '0');
const mmss = (sec: number) => `${pad(Math.floor(sec / 60))}:${pad(sec % 60)}`;

function useNow(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  return now;
}

function Tiles({ data, now }: { data: MonitorView; now: number }) {
  const services = useServices();
  const names = new Map((services.data ?? []).map((s) => [s.code, s.short]));
  const st = data.session.settings;
  // после завершения время замирает на моменте завершения
  const end = data.session.finished_at ? new Date(data.session.finished_at).getTime() : now;
  return (
    <section className="cab-tiles" aria-label="Обучающиеся">
      {data.rows.map(({ participant: p, progress: g }) => {
        const since = g.current_since ? Math.max(0, Math.floor((end - new Date(g.current_since).getTime()) / 1000)) : null;
        const norm = p.role === '112' ? st.norm_112 : st.norm_dds;
        const running = data.session.status === 'running';
        const state: TileState = !running ? 'offline' : since === null ? 'idle' : normStatus(since, norm);
        // п. 3.6: в идущем звонке видно, как оператор ведёт заявителя — эмоция и напряжение 0–10
        const caller = g.caller_emotion && g.caller_tension != null ? ` · заявитель: ${g.caller_emotion}, ${g.caller_tension}/10` : '';
        const label = g.current_card
          ? `№ ${g.current_card}${g.current_label ? ` · ${g.current_label}` : ''}${caller}`
          : p.role === '112' ? 'ждёт вызов' : 'очередь пуста';
        return (
          <StudentTile key={p.student_id} name={p.full_name} initials={initials(p.full_name)}
            role={p.role === '112' ? 'оператор 112' : `ДДС: ${names.get(p.dds_service_code ?? '') ?? p.dds_service_code}`}
            state={state} cardKind={p.role} cardLabel={label} timer={since !== null ? mmss(since) : undefined}
            queue={p.role === 'dds' ? g.waiting : undefined} score={g.avg_score === null ? null : Math.round(g.avg_score)} actions={false} done={String(g.cards_done)}
            errors={g.errors} note={g.last_errors[g.last_errors.length - 1]} />
        );
      })}
    </section>
  );
}

export function SessionMonitorPage() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const q = useMonitor(id);
  const state = useSessionState(id);
  const groups = useIncidentGroups();
  const now = useNow();
  const d = q.data;
  if (!d) {
    return <TeacherShell active="sessions" title="Занятие">{q.isError ? <Banner status="critical">{q.error.message}</Banner> : 'загрузка…'}</TeacherShell>;
  }
  const s = d.session;
  const scores = d.rows.map((r) => r.progress.avg_score).filter((x): x is number => x !== null);
  const avg = scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : null;
  const done = d.rows.reduce((a, r) => a + r.progress.cards_done, 0);
  const errors = d.rows.reduce((a, r) => a + r.progress.errors, 0);
  const elapsed = s.started_at ? Math.floor(((s.finished_at ? new Date(s.finished_at).getTime() : now) - new Date(s.started_at).getTime()) / 1000) : 0;
  const groupTitles = new Map((groups.data ?? []).map((g) => [g.id, g.title]));
  return (
    <TeacherShell active="sessions" crumbs="Пульт / Занятия" title={s.title} subtitle={`${MODE_TITLE[s.mode]} · ${SESSION_STATUS[s.status]}`}
      actions={
        <>
          {s.status === 'planned' && <Button variant="primary" icon="play" disabled={state.isPending} onClick={() => state.mutate(true)}>начать занятие</Button>}
          {s.status === 'running' && <Button variant="danger" icon="stop" disabled={state.isPending} onClick={() => state.mutate(false)}>завершить</Button>}
          {s.status !== 'planned' && <Button icon="bar_chart" onClick={() => navigate(`/teacher/sessions/${id}/report`)}>отчёт</Button>}
        </>
      }>
      {state.isError && <Banner status="critical">{state.error.message}</Banner>}
      {s.status === 'planned' && <Banner>Занятие ещё не начато. После старта обучающиеся увидят его в журнале 112 и в АРМ ДДС.</Banner>}
      <section className="cab-kpis" aria-label="Сводка по занятию">
        <StatTile label="Идёт" value={s.started_at ? mmss(elapsed) : '—'} note={s.started_at ? `с ${new Date(s.started_at).toLocaleTimeString('ru-RU')}` : 'не начато'} />
        <StatTile label="Средний балл" value={avg ?? '—'} note={`порог ${s.settings.threshold}`} />
        <StatTile label="Карточек обработано" value={done} />
        <StatTile label="Ошибок" value={errors} />
      </section>
      <Tiles data={d} now={now} />
      <Card title="Параметры занятия">
        <dl className="tch-dl">
          <dt>Категории</dt><dd>{s.groups.length ? s.groups.map((g) => `${g}. ${groupTitles.get(g) ?? ''}`).join('; ') : 'любые'}</dd>
          <dt>Карточки для ДДС</dt><dd>{SOURCE_TITLE[s.card_source]}</dd>
          <dt>Нормативы</dt><dd>карточка 112 — {s.settings.norm_112} с, решение ДДС — {s.settings.norm_dds} с</dd>
          <dt>Темп</dt><dd>вызов 112 — раз в {s.settings.call_interval_s} с, карточка ДДС — раз в {s.settings.feed_interval_s} с, очередь до {s.settings.max_waiting}</dd>
          <dt>Участники</dt>
          <dd>{s.participants.map((p) => <StatusPill key={p.student_id} status="info">{p.full_name} · {p.role === '112' ? '112' : p.dds_service_code}</StatusPill>)}</dd>
        </dl>
      </Card>
    </TeacherShell>
  );
}
