/** Точка входа SPA: шрифты и стили ui-kit, клиент запросов (повторы только при сбое связи, работа в фоновом окне —
 *  п. 6.1), баннер «нет связи», обучение интерфейсу (п. 5.3) и маршрутизатор. */
import '@fontsource/roboto/300.css';
import '@fontsource/roboto/400.css';
import '@fontsource/roboto/500.css';
import '@fontsource/roboto/700.css';
import '@smena112/ui-kit/index.css';

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider, focusManager } from '@tanstack/react-query';
import { RouterProvider } from 'react-router-dom';
import { router } from './app/router';
import { ConnectionBanner } from './shared/ui/ConnectionBanner';
import { OnboardingProvider } from './shared/onboarding/OnboardingProvider';
import { isTransient } from './shared/api/resilience';

// АРМ работает и в фоновом окне (6.1): TanStack Query по умолчанию ставит повторы на паузу без фокуса, и после
// сбоя в фоне журнал и сигнал о новой карточке замирают. Считаем приложение всегда активным.
focusManager.setEventListener(() => () => undefined);
focusManager.setFocused(true);

// повтор чтения — только при сбое связи (6.1); ошибки прав и правил показываются сразу
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: (n, e) => isTransient(e) && n < 3, retryDelay: 1_500, staleTime: 30_000 } },
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ConnectionBanner />
      <OnboardingProvider>
        <RouterProvider router={router} />
      </OnboardingProvider>
    </QueryClientProvider>
  </StrictMode>,
);
