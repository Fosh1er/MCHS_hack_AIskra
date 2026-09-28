/** Пошаговая подсветка элементов экрана (п. 5.3). Затемнение с «окном» над элементом — четыре полосы и рамка,
 *  подсказка — под, над или сбоку от элемента. Пока идёт обучение, клики по странице и горячие клавиши АРМ
 *  не срабатывают: Esc на карточке 112 закрывает подсказку, а не карточку. */
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from 'react';
import { createPortal } from 'react-dom';
import { Icon } from '@smena112/ui-kit';
import type { TourStep } from './tours';

const GAP = 12; // от элемента до подсказки
const EDGE = 16; // от края окна
const POP_W = 360;
const POP_MIN_H = 200; // сколько места нужно подсказке под или над элементом

/** Первый видимый элемент по селектору: на телефоне меню кабинета — нижняя панель, на десктопе — боковое. */
export function findTarget(selector: string): HTMLElement | null {
  for (const el of document.querySelectorAll<HTMLElement>(selector)) {
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.height > 0) return el;
  }
  return null;
}

/** Шаги, которые есть на экране: цель не найдена — шаг пропускается (нет занятия — нет баннера занятия). */
export const visibleSteps = (steps: TourStep[]) => steps.filter((s) => !s.target || findTarget(s.target));

function popoverStyle(r: DOMRect): CSSProperties {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const width = Math.min(POP_W, vw - 2 * EDGE);
  const left = Math.min(Math.max(r.left, EDGE), vw - width - EDGE);
  const below = vh - r.bottom - GAP;
  const above = r.top - GAP;
  if (below >= POP_MIN_H || (below >= above && below >= POP_MIN_H / 2)) return { top: r.bottom + GAP, left, width };
  if (above >= POP_MIN_H / 2) return { bottom: vh - r.top + GAP, left, width };
  // элемент почти во весь экран (IP-телефон, опросник) — подсказка сбоку
  const top = Math.min(Math.max(r.top, EDGE), vh - POP_MIN_H - EDGE);
  if (r.left - GAP >= width + EDGE) return { top, left: r.left - GAP - width, width };
  return { top, left: Math.min(r.right + GAP, vw - width - EDGE), width };
}

/** «Окно» над элементом с запасом в 4 px, в пределах экрана. */
function cutout(r: DOMRect): { top: number; left: number; width: number; height: number } {
  const pad = 4;
  const top = Math.max(0, r.top - pad);
  const left = Math.max(0, r.left - pad);
  const bottom = Math.min(window.innerHeight, r.bottom + pad);
  const right = Math.min(window.innerWidth, r.right + pad);
  return { top, left, width: Math.max(0, right - left), height: Math.max(0, bottom - top) };
}

export function Tour({ steps, onFinish, onSkip }: {
  steps: TourStep[];
  onFinish: () => void; // дошли до конца или закрыли — экран считается пройденным
  onSkip: () => void; // «пропустить обучение» — больше не показывать
}) {
  const [index, setIndex] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const next = useRef<HTMLButtonElement>(null);
  const pop = useRef<HTMLDivElement>(null);
  const step = steps[index];
  const last = index === steps.length - 1;

  const measure = useCallback(() => {
    const el = step?.target ? findTarget(step.target) : null;
    setRect(el ? el.getBoundingClientRect() : null);
  }, [step]);

  useLayoutEffect(() => {
    const el = step?.target ? findTarget(step.target) : null;
    el?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    measure();
    next.current?.focus({ preventScroll: true });
  }, [step, measure]);

  useEffect(() => {
    window.addEventListener('resize', measure);
    window.addEventListener('scroll', measure, true);
    return () => {
      window.removeEventListener('resize', measure);
      window.removeEventListener('scroll', measure, true);
    };
  }, [measure]);

  const forward = useCallback(() => (last ? onFinish() : setIndex((i) => i + 1)), [last, onFinish]);
  const back = useCallback(() => setIndex((i) => Math.max(0, i - 1)), []);

  // клавиатура — в фазе захвата: до горячих клавиш АРМ (useHotkeys слушает window в фазе всплытия)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const inPopover = pop.current?.contains(e.target as Node) ?? false;
      if (e.key === 'ArrowRight') { e.preventDefault(); forward(); }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); back(); }
      else if (e.key === 'Escape') { e.preventDefault(); onFinish(); }
      else if (!inPopover) { e.preventDefault(); next.current?.focus({ preventScroll: true }); } // ни печати, ни Insert
      e.stopPropagation(); // Enter, пробел и Tab внутри подсказки работают как обычно
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [forward, back, onFinish]);

  if (!step) return null;
  const hole = rect && cutout(rect);

  return createPortal(
    <div className="tour">
      <div className="tour__block" onClick={(e) => e.stopPropagation()} />
      {hole ? (
        <>
          {/* затемнение — четыре полосы вокруг «окна»: огромная тень над часто перерисуемым элементом
              (таймер карточки) Chromium рисует ненадёжно */}
          <div className="tour__dim" style={{ top: 0, left: 0, right: 0, height: hole.top }} />
          <div className="tour__dim" style={{ top: hole.top + hole.height, left: 0, right: 0, bottom: 0 }} />
          <div className="tour__dim" style={{ top: hole.top, height: hole.height, left: 0, width: hole.left }} />
          <div className="tour__dim" style={{ top: hole.top, height: hole.height, left: hole.left + hole.width, right: 0 }} />
          <div className="tour__spot" style={hole} />
        </>
      ) : <div className="tour__dim tour__dim--full" />}
      <div ref={pop} className={`tour__pop${rect ? '' : ' tour__pop--center'}`} style={rect ? popoverStyle(rect) : undefined}
        role="dialog" aria-modal="true" aria-labelledby="tour-title">
        <button type="button" className="tour__close" aria-label="Закрыть подсказки этого экрана (Esc)" onClick={onFinish}>
          <Icon name="close" size="sm" />
        </button>
        <div className="tour__step" aria-live="polite">Шаг {index + 1} из {steps.length}</div>
        <div id="tour-title" className="tour__title">{step.title}</div>
        <p className="tour__body">{step.body}</p>
        {step.list && <ol className="tour__list">{step.list.map((x) => <li key={x}>{x}</li>)}</ol>}
        <div className="tour__foot">
          <button type="button" className="tour__skip" onClick={onSkip}>пропустить обучение</button>
          {index > 0 && <button type="button" className="cab-btn cab-btn--sm" onClick={back}>назад</button>}
          <button ref={next} type="button" className="cab-btn cab-btn--sm cab-btn--primary" onClick={forward}>{last ? 'готово' : 'далее'}</button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
