/** Модальные окна карточки 112 по инструкции и стенду: «Добавьте службы» (image49/стенд), «Список оповещаемых
 *  служб» (image56), «Сохранить карточку как пустую?» (image11–13), закрытие без сохранения. */
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Icon } from '@smena112/ui-kit';
import type { ServiceRow } from '../../shared/api/dictionaries';
import type { PanelService } from './state';

function Modal({ title, onClose, children, wide }: { title?: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { ref.current?.querySelector<HTMLElement>('input, button.arm112-btn')?.focus(); }, []);
  return (
    <div className="arm112-modalwrap" role="dialog" aria-modal="true" aria-label={title}>
      <div className="arm-overlay" onClick={onClose} />
      <div className={wide ? 'arm-modal' : 'arm112-modal'} ref={ref}>
        <button type="button" className="arm-modal__close" aria-label="Закрыть (Esc)" onClick={onClose}><Icon name="close" size="sm" /></button>
        {title && (wide ? <div className="arm-modal__title">{title}</div> : <h2>{title}</h2>)}
        {children}
      </div>
    </div>
  );
}

export function AddServicesModal({ all, selected, onSave, onClose }: {
  all: ServiceRow[]; selected: string[]; onSave: (codes: string[]) => void; onClose: () => void;
}) {
  const [q, setQ] = useState('');
  const [picked, setPicked] = useState(() => new Set(selected));
  const shown = useMemo(() => {
    const words = q.toLowerCase().replace(/ё/g, 'е').split(/\s+/).filter(Boolean);
    const list = all.filter((s) => words.every((w) => `${s.short} ${s.full}`.toLowerCase().replace(/ё/g, 'е').includes(w)));
    return [...list.filter((s) => picked.has(s.code)), ...list.filter((s) => !picked.has(s.code))].slice(0, 200);
  }, [all, q, picked]);
  const toggle = (code: string) => setPicked((p) => { const n = new Set(p); if (n.has(code)) n.delete(code); else n.add(code); return n; });
  return (
    <Modal title="Добавьте службы" onClose={onClose} wide>
      <input className="arm-field__input arm-modal__search" placeholder="Поиск ..." value={q} onChange={(e) => setQ(e.target.value)} aria-label="Поиск службы" />
      <div className="arm-modal__list" style={{ overflowY: 'auto' }} role="listbox" aria-multiselectable="true">
        {shown.map((s) => (
          <div key={s.code} role="option" aria-selected={picked.has(s.code)} tabIndex={0}
            className={`arm-modal__item${picked.has(s.code) ? ' arm-modal__item--on' : ''}`}
            onClick={() => toggle(s.code)} onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), toggle(s.code))}>
            {s.short === s.full ? s.short : `${s.short} (${s.full})`}
          </div>
        ))}
      </div>
      <button type="button" className="arm-modal__btn" onClick={() => onSave([...picked])}>Сохранить и закрыть</button>
    </Modal>
  );
}

export function SaveModal({ services, busy, onConfirm, onClose }: {
  services: PanelService[]; busy: boolean; onConfirm: () => void; onClose: () => void;
}) {
  return (
    <Modal title="Список оповещаемых служб:" onClose={onClose}>
      <div className="arm112-modal__chips">
        {services.length === 0 && <span className="arm-panel__label">Службы не назначены (служебный тип)</span>}
        {services.map((s) => <span key={s.code} className={`arm112-modal__chip${s.main ? ' arm112-modal__chip--main' : ''}`}>{s.short}</span>)}
      </div>
      <div className="arm112-modal__btns">
        <button type="button" className="arm112-btn arm112-btn--primary" onClick={onConfirm} disabled={busy}>оповестить и сохранить карточку</button>
        <button type="button" className="arm112-btn" onClick={onClose}>вернуться к заполнению</button>
      </div>
    </Modal>
  );
}

export function EmptyCardModal({ kind, busy, onConfirm, onClose }: {
  kind: 'no_contact' | 'call_dropped'; busy: boolean; onConfirm: () => void; onClose: () => void;
}) {
  return (
    <Modal title="Сохранить карточку как пустую?" onClose={onClose}>
      <p style={{ marginTop: -8, marginBottom: 18 }}>{kind === 'no_contact' ? 'Нет контакта с заявителем.' : 'Срыв звонка.'} Карточка получит статус «Завершена».</p>
      <div className="arm112-modal__btns">
        <button type="button" className="arm112-btn" onClick={onClose}>вернуться и заполнить</button>
        <button type="button" className="arm112-btn arm112-btn--primary" onClick={onConfirm} disabled={busy}>сохранить карточку как пустую</button>
      </div>
    </Modal>
  );
}

export function CloseCardModal({ onConfirm, onClose }: { onConfirm: () => void; onClose: () => void }) {
  return (
    <Modal title="Закрыть карточку без сохранения?" onClose={onClose}>
      <p style={{ marginTop: -8, marginBottom: 18 }}>Введённые данные будут потеряны, службы не оповещены.</p>
      <div className="arm112-modal__btns">
        <button type="button" className="arm112-btn" onClick={onClose}>вернуться к заполнению</button>
        <button type="button" className="arm112-btn arm112-btn--primary" onClick={onConfirm}>закрыть без сохранения</button>
      </div>
    </Modal>
  );
}
