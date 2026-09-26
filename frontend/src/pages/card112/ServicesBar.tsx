/** Нижняя оранжевая панель «Службы:» (Alt+Z), как на стенде 2026: чипы служб (основная подчёркнута, без интеграции —
 *  серые), ⇕ — второй ряд для служб, которые не поместились, «+» — «Добавьте службы»; справа «сохранить» (Alt+S). */
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Icon, ServiceBar, ServiceTab, SquareButton } from '@smena112/ui-kit';
import type { PanelService } from './state';
import { Hint } from './Hint';

export interface SavedService { code: string; short: string; is_main: boolean; integrated: boolean; status: string }

const LATER = 'появится в следующих пунктах плана';
const CHIP_W = 129; // ширина чипа службы на стенде (CSS-пиксели)
const BUTTONS_W = 2 * 50 + 3 * 16; // ⇕ и «+» с отступами

/** Сколько чипов помещается в первый ряд панели (остальные — во второй ряд по ⇕). */
function useFitCount(total: number): [React.RefObject<HTMLDivElement>, number] {
  const ref = useRef<HTMLDivElement>(null);
  const [fit, setFit] = useState(total);
  useEffect(() => {
    const tabs = ref.current?.querySelector<HTMLElement>('.arm-svcbar__tabs');
    const end = ref.current?.querySelector<HTMLElement>('.arm-svcbar__end');
    const label = ref.current?.querySelector<HTMLElement>('.arm-svcbar__label');
    if (!tabs || !ref.current) return;
    const measure = () => {
      const free = ref.current!.clientWidth - (end?.offsetWidth ?? 0) - (label?.offsetWidth ?? 0) - BUTTONS_W;
      setFit(Math.max(1, Math.floor(free / CHIP_W)));
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, fit];
}

export function ServicesBar({ panel, saved, onRemove, onAdd, onSave, onClose, onNew, busy }: {
  panel: PanelService[];
  saved: SavedService[] | null;
  onRemove: (s: PanelService) => void;
  onAdd: () => void;
  onSave: () => void;
  onClose: () => void;
  onNew: () => void;
  busy: boolean;
}) {
  const chips: { code: string; node: ReactNode }[] = saved
    ? saved.map((s) => ({ code: s.code, node: <ServiceTab name={s.short} main={s.is_main} noIntegration={!s.integrated} status={s.status} /> }))
    : panel.map((s) => ({
        code: s.code,
        node: (
          <span style={{ display: 'flex' }} title={s.auto ? 'подобрана автоматически' : 'добавлена вручную'}>
            <ServiceTab variant="112" name={s.short} main={s.main} noIntegration={!s.integrated} onRemove={() => onRemove(s)} />
          </span>
        ),
      }));
  const [ref, fit] = useFitCount(chips.length);
  const [expanded, setExpanded] = useState(false);
  const first = chips.slice(0, fit);
  const rest = chips.slice(fit);

  const end = (
    <>
      {saved ? (
        <button type="button" className="arm-savebtn" onClick={onNew} title="Insert">новая карточка</button>
      ) : (
        <span className="arm112-rel"><Hint k="Alt+S" /><button id="save-card" type="button" className="arm-savebtn" onClick={onSave} disabled={busy}>сохранить</button></span>
      )}
      <button type="button" className="arm-sqbtn" disabled title={`Связи карточек — ${LATER} (1.6)`} aria-label="Связи"><Icon name="link" /></button>
      <button type="button" className="arm-sqbtn" disabled title={`Напоминание — ${LATER}`} aria-label="Напоминание"><Icon name="timer" /></button>
      <button type="button" className="arm-sqbtn" disabled title={`Перевод вызова — ${LATER} (1.4)`} aria-label="Перевод"><Icon name="hand" /></button>
      <button type="button" className="arm-sqbtn" disabled title={`Важное происшествие — ${LATER}`} aria-label="Важное происшествие"><Icon name="bell" /></button>
      <button type="button" className="arm-sqbtn" disabled title={`Сообщить о проблеме — ${LATER}`} aria-label="Сообщить о проблеме"><Icon name="report" /></button>
      <SquareButton icon="close" label="Закрыть карточку (Esc)" onClick={onClose} />
    </>
  );
  const withKeys = (list: typeof chips) => list.map((c) => <span key={c.code} style={{ display: 'flex' }}>{c.node}</span>);
  return (
    <div className="arm112-rel" ref={ref}>
      <Hint k="Alt+Z" style={{ left: 8 }} />
      <ServiceBar
        variant="112"
        end={end}
        stack={rest.length > 0 ? withKeys(rest) : undefined}
        expanded={expanded && rest.length > 0}
        onToggleExpand={chips.length > 0 ? () => setExpanded((x) => !x) : undefined}
        actions={!saved && (
          <div className="arm112-svcbtns">
            <button id="add-services" type="button" className="arm-sqbtn" aria-label="Добавить службы" onClick={onAdd}><Icon name="plus" /></button>
          </div>
        )}
      >
        {withKeys(first)}
      </ServiceBar>
    </div>
  );
}
