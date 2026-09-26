/** Блок «Адрес» (Alt+A): единая строка с подсказками + поля, как на стенде 2026.
 *  Подсказки — по справочнику округов и районов (0.2); улицы и дома — п. 1.2 (локальный адресный справочник). */
import { useMemo, useState } from 'react';
import { Icon } from '@smena112/ui-kit';
import type { District, Okrug } from '../../shared/api/dictionaries';
import { parseAddressLine, type Action, type CardState } from './state';
import { Hint } from './Hint';

const norm = (s: string) => s.toLowerCase().replace(/ё/g, 'е');

function Field({ label, value, onChange, readOnly, id }: { label: string; value: string; onChange: (v: string) => void; readOnly: boolean; id?: string }) {
  return (
    <label className="arm-field">
      <span className="arm-field__label">{label}:</span>
      <input id={id} className="arm-field__input" value={value} readOnly={readOnly} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

export function AddressBlock({ state, dispatch, okrugs, districts, readOnly }: {
  state: CardState; dispatch: (a: Action) => void; okrugs: Okrug[]; districts: District[]; readOnly: boolean;
}) {
  const a = state.address;
  const [open, setOpen] = useState(false);
  const set = (patch: Partial<CardState['address']>) => dispatch({ type: 'address', patch });
  const okrugShort = useMemo(() => new Map(okrugs.map((o) => [o.code, o.short])), [okrugs]);

  const suggestions = useMemo(() => {
    // основа слова без окончания: «Басманная улица» подсказывает «Басманный» район
    const stems = norm(a.raw).split(/[\s,.]+/).filter((w) => w.length >= 4).map((w) => w.slice(0, Math.max(4, w.length - 2)));
    if (!stems.length) return [];
    return districts
      .filter((d) => [d.name, ...d.aliases].some((n) => stems.some((st) => norm(n).split(/[\s-]+/).some((part) => part.startsWith(st)))))
      .slice(0, 8);
  }, [a.raw, districts]);

  const pickDistrict = (d: District) => {
    set({ district: d.code, okrug: d.okrug });
    setOpen(false);
  };
  const applyLine = () => {
    if (a.raw.trim()) set(parseAddressLine(a.raw));
  };

  return (
    <div className="arm-panel arm112-address arm112-rel" style={{ padding: '10px 10px 14px' }}>
      <Hint k="Alt+A" />
      <div className="arm-panel__label" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        Адрес: <Icon name="place" size="sm" title="Карта и координаты — п. 1.2" />
      </div>
      <div className="arm112-address__line">
        <input
          id="address-line" className="arm-field__input" placeholder="введите адрес" value={a.raw} readOnly={readOnly} autoComplete="off"
          onChange={(e) => { set({ raw: e.target.value }); setOpen(true); }}
          onBlur={() => { applyLine(); setTimeout(() => setOpen(false), 150); }}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); applyLine(); if (suggestions[0]) pickDistrict(suggestions[0]); } }}
        />
        {!readOnly && <button type="button" className="arm-iconsq" style={{ border: 0, background: 'none' }} aria-label="Очистить адрес" onClick={() => dispatch({ type: 'clearAddress' })}><Icon name="close" size="sm" /></button>}
      </div>
      {open && !readOnly && suggestions.length > 0 && (
        <div className="arm112-suggest" role="listbox" style={{ top: 58 }}>
          {suggestions.map((d) => (
            <button key={d.code} type="button" role="option" onMouseDown={(e) => e.preventDefault()} onClick={() => pickDistrict(d)}>
              {d.name}<small>{d.kind === 'settlement' ? 'поселение' : 'район'}, {okrugShort.get(d.okrug)}</small>
            </button>
          ))}
        </div>
      )}

      <div className="arm112-grid arm112-grid--3">
        <Field label="Страна" value={a.country} readOnly={readOnly} onChange={(v) => set({ country: v })} />
        <Field label="Субъект" value={a.region} readOnly={readOnly} onChange={(v) => set({ region: v })} />
        <Field label="Населенный пункт" value={a.city} readOnly={readOnly} onChange={(v) => set({ city: v })} />
      </div>
      <div className="arm112-grid arm112-grid--addr2">
        <Field label="Объект" value={a.object} readOnly={readOnly} onChange={(v) => set({ object: v })} />
        <label className="arm-field">
          <span className="arm-field__label">Округ:</span>
          <select className="arm-uline arm-uline--select" value={a.okrug ?? ''} disabled={readOnly}
            onChange={(e) => set({ okrug: e.target.value || null, district: null })}>
            <option value="" />
            {okrugs.map((o) => <option key={o.code} value={o.code}>{o.short}</option>)}
          </select>
        </label>
        <label className="arm-field">
          <span className="arm-field__label">Район:</span>
          <select className="arm-uline arm-uline--select" value={a.district ?? ''} disabled={readOnly}
            onChange={(e) => { const d = districts.find((x) => x.code === e.target.value); set({ district: d?.code ?? null, okrug: d?.okrug ?? a.okrug }); }}>
            <option value="" />
            {districts.filter((d) => !a.okrug || d.okrug === a.okrug).map((d) => <option key={d.code} value={d.code}>{d.name}</option>)}
          </select>
        </label>
      </div>
      <div className="arm112-grid arm112-grid--3">
        <Field label="Улица" value={a.street} readOnly={readOnly} onChange={(v) => set({ street: v })} />
        <Field label="Дом/Вл" value={a.house} readOnly={readOnly} onChange={(v) => set({ house: v })} />
        <Field label="Корпус" value={a.building} readOnly={readOnly} onChange={(v) => set({ building: v })} />
      </div>
      <div className="arm112-grid arm112-grid--5">
        <Field label="Стр/соор" value={a.structure} readOnly={readOnly} onChange={(v) => set({ structure: v })} />
        <Field label="Квартира/офис" value={a.flat} readOnly={readOnly} onChange={(v) => set({ flat: v })} />
        <Field label="Подъезд" value={a.entrance} readOnly={readOnly} onChange={(v) => set({ entrance: v })} />
        <Field label="Этаж" value={a.floor} readOnly={readOnly} onChange={(v) => set({ floor: v })} />
        <Field label="Код" value={a.code} readOnly={readOnly} onChange={(v) => set({ code: v })} />
      </div>
      <label className="arm-field" style={{ marginTop: 10 }}>
        <span className="arm-field__label">Описательный адрес:</span>
        <textarea className="arm112-textarea" rows={2} value={a.descriptive} readOnly={readOnly} onChange={(e) => set({ descriptive: e.target.value })} />
      </label>
      {!readOnly && <button type="button" className="arm-minibtn arm112-minibtn" onClick={() => dispatch({ type: 'clearAddress' })}>очистить адрес</button>}
    </div>
  );
}

export function DescriptionBlock({ state, dispatch, ambulance, readOnly }: {
  state: CardState; dispatch: (a: Action) => void; ambulance: boolean; readOnly: boolean;
}) {
  const len = state.description.length;
  return (
    <div className="arm-panel arm-panel--fill arm112-rel">
      <Hint k="Alt+O" />
      <label className="arm-field">
        <span className="arm-field__label">Описание со слов заявителя</span>
        <textarea id="description" className="arm112-textarea" rows={3} placeholder="введите" value={state.description} readOnly={readOnly}
          onChange={(e) => dispatch({ type: 'description', value: e.target.value })} />
      </label>
      <div className="arm112-counter">{len} / 1999</div>
      {ambulance && len > 100 && (
        <div className="arm112-warn" role="status">Служба 03 получит только первые 100 символов: «{state.description.slice(0, 100)}»</div>
      )}
    </div>
  );
}
