/** Горячие клавиши АРМ-112 (docs/brief/03 §6). Сравнение по `event.code` — не зависит от раскладки (рус/лат)
 *  и от символов, которые macOS подставляет при Option+буква. Зажатый Alt показывает подсказки. */
import { useEffect, useRef, useState } from 'react';

export type HotkeyMap = Record<string, () => void>;

/** Код клавиши. Если браузер или виртуальная клавиатура не передали `code`, выводим его из `key`. */
export function keyCode(e: Pick<KeyboardEvent, 'code' | 'key'>): string {
  if (e.code) return e.code;
  if (/^[a-z]$/i.test(e.key)) return `Key${e.key.toUpperCase()}`;
  if (/^\d$/.test(e.key)) return `Digit${e.key}`;
  return e.key; // Insert, Escape, F1…
}

/** Карты обработчиков можно пересоздавать на каждом рендере: слушатель один, берёт актуальные из ref. */
export function useHotkeys(alt: HotkeyMap, plain: HotkeyMap): boolean {
  const [altHeld, setAltHeld] = useState(false);
  const maps = useRef({ alt, plain });
  maps.current = { alt, plain };
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === 'Alt') { setAltHeld(true); return; }
      const { alt: a, plain: p } = maps.current;
      const code = keyCode(e);
      const handler = e.altKey ? a[code] : !e.ctrlKey && !e.metaKey ? p[code] : undefined;
      if (handler) {
        e.preventDefault();
        setAltHeld(false);
        handler();
      }
    };
    const up = (e: KeyboardEvent) => { if (e.key === 'Alt') setAltHeld(false); };
    const blur = () => setAltHeld(false);
    window.addEventListener('keydown', down);
    window.addEventListener('keyup', up);
    window.addEventListener('blur', blur);
    return () => {
      window.removeEventListener('keydown', down);
      window.removeEventListener('keyup', up);
      window.removeEventListener('blur', blur);
    };
  }, []);
  return altHeld;
}

/** Фокус на элемент по id (поле, кнопка, опросная карта). */
export const focusId = (id: string) => () => document.getElementById(id)?.focus();
