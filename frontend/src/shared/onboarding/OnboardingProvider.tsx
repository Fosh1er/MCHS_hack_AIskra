/** Обучение интерфейсу (п. 5.3, 5.4): какой экран открыт, показать ли подсказки и куда записать прогресс.
 *  Страница регистрирует свой экран через `useScreenTour(id, ready)`; когда данные экрана загружены (`ready`),
 *  новичку показываются подсказки этого экрана, а перед самым первым — обзор маршрута его роли. Сами подсказки
 *  показываются только своей аудитории (обучающемуся — его экраны, преподавателю — свои), чужие — по кнопке. */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Button, SquareButton } from '@smena112/ui-kit';
import { useMe } from '../api/auth';
import { useOnboarding, useUpdateOnboarding } from '../api/onboarding';
import { Tour, visibleSteps } from './Tour';
import { ALL_TOURS, WELCOMES, tourAudience, type TourId, type TourStep } from './tours';

interface Controls {
  register: (id: TourId, ready: boolean) => void;
  unregister: (id: TourId) => void;
  screen: TourId | null;
  replay: () => void; // подсказки текущего экрана ещё раз
  active: { id: TourId; auto: boolean } | null; // идут подсказки экрана; auto — показаны сами, а не по кнопке
  restart: () => void; // «пройти обучение заново»: сбросить прогресс
}

const Ctx = createContext<Controls | null>(null);

interface Active { key: number; id: TourId; auto: boolean; ids: string[]; steps: TourStep[] }

export function OnboardingProvider({ children }: { children: ReactNode }) {
  const me = useMe().data;
  const state = useOnboarding(!!me);
  const update = useUpdateOnboarding();
  const [screen, setScreen] = useState<{ id: TourId; ready: boolean } | null>(null);
  const [active, setActive] = useState<Active | null>(null);
  const started = useRef(new Set<string>()); // уже показанные в этой вкладке: не ждать ответа сервера

  useEffect(() => { started.current.clear(); setActive(null); }, [me?.user_id]);

  const start = useCallback((id: TourId, welcome: boolean, auto: boolean) => {
    const intro = WELCOMES[tourAudience(id)];
    const steps = visibleSteps([...(welcome ? intro.steps : []), ...ALL_TOURS[id]]);
    if (!steps.length) return;
    const ids = welcome ? [intro.id, id] : [id];
    ids.forEach((x) => started.current.add(x));
    setActive({ key: Date.now(), id, auto, ids, steps });
  }, []);

  // автозапуск: только экраны своей аудитории, если не пропустил обучение и экран не пройден
  const s = state.data;
  useEffect(() => {
    if (!screen?.ready || active || !s?.enabled || s.dismissed) return;
    if (s.audience !== tourAudience(screen.id)) return; // преподаватель в журнале 112 — не обучающийся
    if (s.seen.includes(screen.id) || started.current.has(screen.id)) return;
    const welcome = WELCOMES[tourAudience(screen.id)].id;
    start(screen.id, !s.seen.includes(welcome) && !started.current.has(welcome), true);
  }, [screen, s, active, start]);

  // ушли с экрана посреди подсказок — закрыть их, экран не считается пройденным
  useEffect(() => {
    if (active && screen && !active.ids.includes(screen.id)) setActive(null);
  }, [screen, active]);

  // обзор и экран — одной записью: при перезагрузке сразу после закрытия отметка не теряется (п. 5.4, R5.4-08)
  const finish = () => {
    const ids = active?.ids ?? [];
    setActive(null);
    if (ids.length) update.mutate({ action: 'seen', tours: ids });
  };
  const skip = () => {
    setActive(null);
    update.mutate({ action: 'dismiss' });
  };

  const register = useCallback((id: TourId, ready: boolean) => setScreen({ id, ready }), []);
  const unregister = useCallback((id: TourId) => setScreen((cur) => (cur?.id === id ? null : cur)), []);
  const replay = useCallback(() => { if (screen) start(screen.id, false, false); }, [screen, start]);
  const restart = useCallback(() => {
    started.current.clear();
    update.mutate({ action: 'reset' }, { onSuccess: () => { if (screen) start(screen.id, true, true); } });
  }, [screen, start, update]);

  const activeId = active?.id;
  const activeAuto = active?.auto;
  const value = useMemo(
    () => ({
      register, unregister, screen: screen?.id ?? null, replay, restart,
      active: activeId ? { id: activeId, auto: !!activeAuto } : null,
    }),
    [register, unregister, screen, replay, restart, activeId, activeAuto],
  );

  return (
    <Ctx.Provider value={value}>
      {children}
      {active && <Tour key={active.key} steps={active.steps} onFinish={finish} onSkip={skip} />}
    </Ctx.Provider>
  );
}

/** Экран с подсказками: покажутся при первом открытии своей аудитории, когда `ready` (данные экрана загружены). */
export function useScreenTour(id: TourId, ready = true): void {
  const ctx = useContext(Ctx);
  const register = ctx?.register;
  const unregister = ctx?.unregister;
  useEffect(() => {
    register?.(id, ready);
  }, [register, id, ready]);
  useEffect(() => () => unregister?.(id), [unregister, id]);
}

/** Какие подсказки идут сейчас: карточка 112 ставит таймер на паузу, пока новичок проходит их впервые. */
export function useActiveTour(): { id: TourId; auto: boolean } | null {
  return useContext(Ctx)?.active ?? null;
}

/** Учебный таймер экрана стоит, пока подсказки этого экрана показаны автоматически — в первый раз (п. 5.3): время
 *  инструктажа не идёт в норматив. Ручной повтор по кнопке таймер не останавливает — иначе это лазейка «остановить
 *  время». `set` ставит и снимает паузу на сервере; `onEnd` получает длительность паузы сразу (чтобы цифры на экране
 *  не прыгнули), `onSynced` — после ответа сервера. Возвращает начало текущей паузы (Date.now) или null. */
export function useTourPause(tour: TourId, enabled: boolean, handlers: {
  set: (paused: boolean) => Promise<unknown>;
  onEnd?: (ms: number) => void;
  onSynced?: () => void;
}): number | null {
  const active = useActiveTour();
  const pausing = enabled && active?.id === tour && active.auto;
  const [since, setSince] = useState<number | null>(null);
  const latest = useRef(handlers);
  latest.current = handlers;
  useEffect(() => {
    if (!pausing) return;
    const started = Date.now();
    setSince(started);
    void latest.current.set(true).catch(() => undefined);
    return () => {
      setSince(null);
      latest.current.onEnd?.(Date.now() - started);
      void latest.current.set(false).catch(() => undefined).finally(() => latest.current.onSynced?.());
    };
  }, [pausing]);
  return since;
}

/** Кнопки «обучение» и «пройти обучение заново». */
export function useTourControls() {
  const ctx = useContext(Ctx);
  return { available: !!ctx?.screen, replay: ctx?.replay ?? (() => undefined), restart: ctx?.restart ?? (() => undefined) };
}

/** Кнопка «подсказки» в шапке кабинета преподавателя (п. 5.4): подсказки открытого экрана ещё раз. */
export function TourCabinetButton() {
  const tour = useTourControls();
  if (!tour.available) return null;
  return <span data-tour="help"><Button icon="help" variant="ghost" onClick={tour.replay}>подсказки</Button></span>;
}

/** Квадратная кнопка «?» для экранов без шапки АРМ (карточка 112, карточка ДДС) — в ряду кнопок панели служб. */
export function TourHelpButton() {
  const tour = useTourControls();
  if (!tour.available) return null;
  return <span data-tour="help" style={{ display: 'flex' }}><SquareButton icon="help" label="Подсказки по кнопкам этого экрана" onClick={tour.replay} /></span>;
}
