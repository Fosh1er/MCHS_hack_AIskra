/** Обучение интерфейсу (п. 5.3): какой экран открыт, показать ли подсказки и куда записать прогресс.
 *  Страница регистрирует свой экран через `useScreenTour(id, ready)`; когда данные экрана загружены (`ready`),
 *  новому обучающемуся показываются подсказки этого экрана, а перед самым первым — обзор маршрута (WELCOME). */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { SquareButton } from '@smena112/ui-kit';
import { useMe } from '../api/auth';
import { useOnboarding, useUpdateOnboarding } from '../api/onboarding';
import { Tour, visibleSteps } from './Tour';
import { TOURS, WELCOME, WELCOME_ID, type TourId, type TourStep } from './tours';

interface Controls {
  register: (id: TourId, ready: boolean) => void;
  unregister: (id: TourId) => void;
  screen: TourId | null;
  replay: () => void; // подсказки текущего экрана ещё раз
  restart: () => void; // «пройти обучение заново»: сбросить прогресс
}

const Ctx = createContext<Controls | null>(null);

interface Active { key: number; ids: string[]; steps: TourStep[] }

export function OnboardingProvider({ children }: { children: ReactNode }) {
  const me = useMe().data;
  const state = useOnboarding(!!me);
  const update = useUpdateOnboarding();
  const [screen, setScreen] = useState<{ id: TourId; ready: boolean } | null>(null);
  const [active, setActive] = useState<Active | null>(null);
  const started = useRef(new Set<string>()); // уже показанные в этой вкладке: не ждать ответа сервера

  useEffect(() => { started.current.clear(); setActive(null); }, [me?.user_id]);

  const start = useCallback((id: TourId, welcome: boolean) => {
    const steps = visibleSteps([...(welcome ? WELCOME : []), ...TOURS[id]]);
    if (!steps.length) return;
    const ids = welcome ? [WELCOME_ID, id] : [id];
    ids.forEach((x) => started.current.add(x));
    setActive({ key: Date.now(), ids, steps });
  }, []);

  // автозапуск: только обучающемуся, если не пропустил обучение и экран не пройден
  const s = state.data;
  useEffect(() => {
    if (!screen?.ready || active || !s?.enabled || s.dismissed) return;
    if (s.seen.includes(screen.id) || started.current.has(screen.id)) return;
    start(screen.id, !s.seen.includes(WELCOME_ID) && !started.current.has(WELCOME_ID));
  }, [screen, s, active, start]);

  // ушли с экрана посреди подсказок — закрыть их, экран не считается пройденным
  useEffect(() => {
    if (active && screen && !active.ids.includes(screen.id)) setActive(null);
  }, [screen, active]);

  const finish = async () => {
    const ids = active?.ids ?? [];
    setActive(null);
    for (const tour of ids) await update.mutateAsync({ action: 'seen', tour }).catch(() => undefined);
  };
  const skip = () => {
    setActive(null);
    update.mutate({ action: 'dismiss' });
  };

  const register = useCallback((id: TourId, ready: boolean) => setScreen({ id, ready }), []);
  const unregister = useCallback((id: TourId) => setScreen((cur) => (cur?.id === id ? null : cur)), []);
  const replay = useCallback(() => { if (screen) start(screen.id, false); }, [screen, start]);
  const restart = useCallback(() => {
    started.current.clear();
    update.mutate({ action: 'reset' }, { onSuccess: () => { if (screen) start(screen.id, true); } });
  }, [screen, start, update]);

  const value = useMemo(() => ({ register, unregister, screen: screen?.id ?? null, replay, restart }),
    [register, unregister, screen, replay, restart]);

  return (
    <Ctx.Provider value={value}>
      {children}
      {active && <Tour key={active.key} steps={active.steps} onFinish={() => { void finish(); }} onSkip={skip} />}
    </Ctx.Provider>
  );
}

/** Экран обучающегося: подсказки покажутся при первом открытии, когда `ready` (данные экрана загружены). */
export function useScreenTour(id: TourId, ready = true): void {
  const ctx = useContext(Ctx);
  const register = ctx?.register;
  const unregister = ctx?.unregister;
  useEffect(() => {
    register?.(id, ready);
  }, [register, id, ready]);
  useEffect(() => () => unregister?.(id), [unregister, id]);
}

/** Кнопки «обучение» и «пройти обучение заново». */
export function useTourControls() {
  const ctx = useContext(Ctx);
  return { available: !!ctx?.screen, replay: ctx?.replay ?? (() => undefined), restart: ctx?.restart ?? (() => undefined) };
}

/** Квадратная кнопка «?» для экранов без шапки АРМ (карточка 112, карточка ДДС) — в ряду кнопок панели служб. */
export function TourHelpButton() {
  const tour = useTourControls();
  if (!tour.available) return null;
  return <span data-tour="help" style={{ display: 'flex' }}><SquareButton icon="help" label="Подсказки по кнопкам этого экрана" onClick={tour.replay} /></span>;
}
