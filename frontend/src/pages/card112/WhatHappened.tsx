/** «Что случилось?» (Alt+T): поиск типа с синонимами, плашки частых типов, значимые типы (Alt+R). */
import { useState } from 'react';
import { useCardTypeSearch, type CardType } from '../../shared/api/dictionaries';
import { Hint } from './Hint';

export const cardTypeLabel = (t: Pick<CardType, 'code' | 'title'>) => (/^\d+$/.test(t.code) ? `Происшествие ${t.title}` : t.title);

export function WhatHappened({ all, selected, onAdd, readOnly }: {
  all: CardType[]; selected: string[]; onAdd: (code: string) => void; readOnly: boolean;
}) {
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const [cursor, setCursor] = useState(0);
  const search = useCardTypeSearch(q);
  const options = (q.trim() ? search.data ?? [] : all).filter((t) => !selected.includes(t.code));
  const quick = all.filter((t) => t.quick && !selected.includes(t.code));
  const significant = all.filter((t) => t.significant && !selected.includes(t.code));

  const add = (code: string) => {
    onAdd(code);
    setQ('');
    setOpen(false);
    setCursor(0);
  };

  if (readOnly) return null;
  return (
    <div className="arm112-types arm112-rel">
      <Hint k="Alt+T" />
      <div className={`arm112-types__label${open ? ' arm112-types__label--active' : ''}`}>Введите тип происшествия</div>
      <input
        id="what-happened" className="arm-typeinput" autoComplete="off" value={q}
        placeholder={selected.length ? 'добавить тип происшествия' : 'что случилось?'}
        role="combobox" aria-expanded={open} aria-controls="what-happened-list"
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onChange={(e) => { setQ(e.target.value); setOpen(true); setCursor(0); }}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') { e.preventDefault(); setCursor((c) => Math.min(c + 1, options.length - 1)); }
          if (e.key === 'ArrowUp') { e.preventDefault(); setCursor((c) => Math.max(c - 1, 0)); }
          if (e.key === 'Enter' && options[cursor]) { e.preventDefault(); add(options[cursor].code); }
        }}
      />
      {open && options.length > 0 && (
        <div id="what-happened-list" className="arm112-suggest" role="listbox" style={{ top: 64 }}>
          {options.map((t, i) => (
            <button key={t.code} type="button" role="option" aria-selected={i === cursor} onMouseDown={(e) => e.preventDefault()} onClick={() => add(t.code)}>
              {t.title}
              {q && t.synonyms.length > 0 && <small>{t.synonyms.slice(0, 4).join(', ')}</small>}
            </button>
          ))}
        </div>
      )}
      {selected.length === 0 && (
        <>
          <div className="arm-chips" style={{ marginTop: 16, gap: '10px 14px' }}>
            {quick.map((t) => <button key={t.code} type="button" className="arm-chip" onClick={() => add(t.code)}>{t.title}</button>)}
          </div>
          <div className="arm112-significant arm112-rel">
            <Hint k="Alt+R" />
            Значимые типы происшествий:
            {significant.map((t, i) => (
              <button key={t.code} id={i === 0 ? 'significant-first' : undefined} type="button" onClick={() => add(t.code)}>{t.title}</button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
