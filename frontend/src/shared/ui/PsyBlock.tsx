/** Блок «Работа с заявителем» (п. 3.7): критерии и лента разбора «реплика → действия → состояние заявителя».
 *  Методика — docs/research/psychology/05; основания — профстандарт 12.002, пособия ЦЭПП МЧС, шкала ECCS IAED. */
import { useState } from 'react';
import { Icon } from '@smena112/ui-kit';
import type { PsyBlock as Block, PsyTimelineItem } from '../api/assessment';
import { num } from '../format';

const LEVEL = ['', 'спокоен', 'тревожен', 'расстроен', 'не сотрудничает', 'неуправляем'];

export function PsyLevels({ level, title }: { level: number | null | undefined; title?: string }) {
  if (!level) return null;
  return (
    <span className="psy-levels" role="img" aria-label={`Состояние заявителя: ${level} из 5, ${LEVEL[level]}`} title={title ?? `${level} из 5 — ${LEVEL[level]}`}>
      {[1, 2, 3, 4, 5].map((i) => <i key={i} className={`${i <= level ? 'is-on' : ''}${i <= level && level >= 4 ? ' is-hot' : ''}`} />)}
    </span>
  );
}

function mmss(s: number) {
  const v = Math.max(0, Math.round(s));
  return `${Math.floor(v / 60)}:${String(v % 60).padStart(2, '0')}`;
}

export function PsyTimeline({ items }: { items: PsyTimelineItem[] }) {
  return (
    <ol className="psy-timeline" aria-label="Лента разбора звонка">
      {items.filter((t) => t.speaker !== 'system').map((t, i) => (
        <li key={i}>
          <span className="psy-timeline__at">{mmss(t.at_s)}</span>
          <span className="psy-timeline__who">{t.speaker === 'operator' ? 'Вы' : 'Заявитель'}</span>
          <span>
            {t.speaker === 'party' && t.remarks && t.remarks.length > 0 && <em>({t.remarks.join(', ')}) </em>}
            {t.text}
            {t.speaker === 'party' && <> <PsyLevels level={t.level} /></>}
            {t.blocked && <em className="assess__na"> — не смог сообщить в этом состоянии</em>}
          </span>
          {t.speaker === 'operator' && (t.acts?.length ?? 0) > 0 && (
            <span className="psy-timeline__acts">
              {t.acts!.map((a) => (
                <span key={a.code} className={`psy-act${a.good ? '' : ' psy-act--bad'}`} title={a.why || a.title}>{a.good ? '✓' : '✗'} {a.title}</span>
              ))}
              {t.level_before != null && t.level_after != null && t.level_before !== t.level_after && (
                <span className={`psy-act${t.level_after > t.level_before ? ' psy-act--bad' : ''}`}>
                  состояние {t.level_before} → {t.level_after}
                </span>
              )}
            </span>
          )}
        </li>
      ))}
    </ol>
  );
}

export function PsyBlockView({ block }: { block: Block }) {
  const [showTimeline, setShowTimeline] = useState(false);
  if (block.paused) return <div className="assess__psy"><p className="assess__note">Работа с заявителем: {block.note}</p></div>;
  const st = block.stats;
  return (
    <div className="assess__psy" aria-label="Работа с заявителем">
      <div className="assess__psy-head">
        <b>Работа с заявителем в стрессе</b>
        <span>{st.title}</span>
        <span>состояние {st.start} → {st.final} <PsyLevels level={st.final} /></span>
        {block.score != null && (
          <span className={`assess__score ${block.passed ? 'assess__score--ok' : 'assess__score--bad'}`}>
            {num(block.score)} / 100 · {block.passed ? 'зачтено' : 'не зачтено'}
          </span>
        )}
        <span className="assess__na">{block.weight ? `вес в итоге ${Math.round(block.weight * 100)} %` : 'отдельно от итога'}</span>
      </div>
      {(block.critical?.length ?? 0) > 0 && (
        <p className="assess__note assess__note--critical">Критическая ошибка в работе с заявителем: {block.critical!.join(', ')}.</p>
      )}
      <ul className="assess__list">
        {(block.criteria ?? []).map((c) => (
          <li key={c.key} className="assess__item">
            <span className="assess__title" title={c.note}>{c.title}</span>
            {c.score == null
              ? <span className="assess__na" title={c.note}>{c.note || 'не проверено'}</span>
              : <span className="assess__bar" aria-label={`${Math.round(c.score * 100)} %`}><span style={{ width: `${Math.round(c.score * 100)}%` }} className={c.score >= 0.7 ? 'ok' : c.score >= 0.4 ? 'warn' : 'bad'} /></span>}
            {c.errors.length > 0 && <ul className="assess__errors">{c.errors.map((e) => <li key={e}>{e}</li>)}</ul>}
          </li>
        ))}
      </ul>
      {(block.timeline?.length ?? 0) > 0 && (
        <button type="button" className="assess__toggle" aria-expanded={showTimeline} onClick={() => setShowTimeline(!showTimeline)}>
          <Icon name={showTimeline ? 'expand_less' : 'expand_more'} size="sm" /> Разбор звонка по репликам
        </button>
      )}
      {showTimeline && block.timeline && <PsyTimeline items={block.timeline} />}
      <p className="assess__psy-sources">
        Методика: профстандарт 12.002 (приказ Минтруда № 681н), пособия ЦЭПП МЧС России 2012 и 2023, «Первая помощь» Минздрава 2025,
        шкала ECCS IAED, APCO/NENA ANS 1.107.2-2025.{st.sources?.length ? ` Источники профиля: ${st.sources.join(', ')}.` : ''}
      </p>
    </div>
  );
}
