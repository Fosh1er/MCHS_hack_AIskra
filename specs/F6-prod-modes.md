# F6.3, D4 — Режимы окружения prod/demo/dev и нестабильный тест

- **Приоритет:** P0 · **Статус:** ✅ реализовано (отклонения — §6)
- **Ветка:** `feat/F6-prod-modes` · **Решения:** [ADR-0015](../docs/adr/0015-environment-modes.md) «Режимы окружения prod/demo/dev»
- **Зависит от:** [F2](F2-demo-login.md) (режим `AISKRA_APP_ENV`, демо-вход), [6.2](6.2-security.md) (безопасность) · **Используется в:** F6.4 (CI, smoke в docker compose), F6.7 (стенд, мониторинг `/health`)

## 1. Пункт плана
> **6.3 Режимы окружения (ADR-0015).**
> `AISKRA_APP_ENV`:
> - **prod** — контур заказчика: нет демо-входа (F2), нет `/dev/*`; Swagger только для администратора; cookie `Secure`; уровень логов INFO; внешний ИИ только при явном `allow_external`;
> - **demo** — публичный стенд: демо-вход, баннер «синтетические данные», индикатор генерации ИИ (F1);
> - **dev** — разработка.
>
> **Проверка при старте:** в prod без TLS-cookie, с паролем БД по умолчанию или с `fake` в `ai.default_provider` при включённых ИИ-функциях → отказ запуска с понятным сообщением (fail fast). `/health` отдаёт режим и версию (git sha).
>
> **D4.** Нестабильный тест (≈1 из 15 прогонов, время или нагрузка) — `tests/integration/test_teacher_analytics.py`, отмечен в PR #35/#43 — найти и починить, 20 прогонов подряд без падений.
>
> Источник — [техспека бэклога финала](../docs/brief/07_Бэклог_финала_техспека.md), разделы 6.2 (D1, D4), 6.3, 6.9.

## 2. Требования
| ID | Требование | Источник |
|---|---|---|
| RF6-01 | prod: демо-входа нет (404, нет в схеме API) | техспека 6.3, F2 |
| RF6-02 | prod: маршрутов `/dev/*` нет; страница «ИИ-модели» — только администратору | техспека 6.3, 6.9 |
| RF6-03 | prod: `/docs` и `/openapi.json` — только вошедшему администратору | техспека 6.3 |
| RF6-04 | prod: cookie сессии `Secure`, уровень логов не подробнее INFO | техспека 6.3 |
| RF6-05 | prod: запуск отклоняется сразу с понятным сообщением по-русски, если cookie без `Secure`, пароль БД пустой или по умолчанию, пароль администратора по умолчанию или слабый, `allow_external: true` без явного разрешения переменной. В demo и dev — только предупреждения в лог | техспека 6.3, задача F6.3 |
| RF6-06 | Переопределение для учебного контура — осторожное и задокументированное | задача F6.3 |
| RF6-07 | `/health`: режим, версия (sha из `AISKRA_VERSION`, задаётся при сборке образа: `ARG`/`ENV` в `backend/Dockerfile`; иначе `unknown`), время старта | техспека 6.3, задача F6.3 |
| RF6-08 | ADR-0015 по шаблону и строка в `docs/adr/README.md` | задача F6.3 |
| RF6-09 | D4: найти нестабильные тесты (20 прогонов подряд, случайный порядок, нагрузка), исправить причину, а не ретраями; 20 прогонов подряд без падений | техспека 6.2 D4 |
| RF6-10 | Тесты на RF6-01…07; `test_security.py` — при изменении публичных маршрутов | задача F6.3, AGENTS.md «Безопасность» |
| RF6-11 | Документы: эта спецификация, `docs/demo/Стенд_и_скринкаст.md`, `.env.example`, строка в AGENTS.md | задача F6.3 |

## 3. Трассировка
База путей бэкенда — `backend/src/aiskra/`, тестов — `backend/tests/`.

| ID | Реализация | Проверка | Статус | Примечание |
|---|---|---|---|---|
| RF6-01 | `main.py`: `demo_router` только при `settings.demo_enabled` (F2) | `integration/test_prod_mode.py::test_prod_has_no_demo_or_dev_routes_and_swagger_is_admin_only`; `integration/test_demo_login.py::test_prod_has_no_demo_routes`; `integration/test_security.py::test_demo_public_routes_absent_in_prod` | ✅ | |
| RF6-02 | Страница перенесена: `frontend/src/app/router.tsx` (`/admin/ai`, `RequireAuth system.manage`), `shared/ui/adminMenu.ts`, `shared/ui/CabinetShell.tsx`; сервер — `/api/v1/system/ai*` под `system.manage` (без изменений) | `integration/test_prod_mode.py::test_prod_has_no_demo_or_dev_routes_and_swagger_is_admin_only` (нет путей `/dev`, `GET /dev/ai` → 404); `integration/test_security.py::test_prod_public_routes_outside_api`; `make fe-build` | ✅ | Решение и обоснование — ADR-0015: `/dev` нет ни в одном режиме, диагностика — раздел кабинета администратора |
| RF6-03 | `platform/api_docs.py:mount_admin_docs` (`require(Permission.SYSTEM_MANAGE)`, `include_in_schema=False`); `main.py`: встроенные `/docs` и `/openapi.json` выключены при `settings.docs_admin_only` (prod); `expose_docs=false` выключает их везде | `integration/test_prod_mode.py::test_prod_has_no_demo_or_dev_routes_and_swagger_is_admin_only` (401 без входа, 403 обучающемуся, 200 администратору), `::test_access_denied_to_swagger_is_audited`, `::test_demo_and_dev_keep_public_swagger`, `::test_expose_docs_false_hides_swagger_in_prod_too` | ✅ | |
| RF6-04 | `startup_checks.py` (`cookie_insecure`); `settings.py:effective_log_level`; `main.py`: `basicConfig` и уровень корневого логгера | `unit/test_startup_checks.py::test_prod_refuses_unsafe_settings[…cookie…]`, `::test_prod_log_level_not_below_info`; `integration/test_prod_mode.py` (`Set-Cookie: … Secure`) | ✅ | |
| RF6-05 | `platform/startup_checks.py`: `find_problems` → `check_startup` (prod — `UnsafeConfigError` со всеми проблемами сразу; demo/dev — `log.warning`); вызов — `main.py:create_app` и `cli.py check-config` (первым шагом `CMD` в `backend/Dockerfile`, до миграций и `ensure-admin`; `ensure-admin` тоже проверяет). `main.py`: `UnsafeConfigError` → `SystemExit` без трассировки. `settings.py`: `ai_allow_external` (`AISKRA_AI_ALLOW_EXTERNAL`) | `unit/test_startup_checks.py` (все коды, все проблемы сразу, секреты не попадают в сообщение, SQLite и отсутствие пароля администратора, `test_demo_and_dev_only_warn`, `test_cli_check_config_uses_same_rules`); `integration/test_prod_mode.py::test_unsafe_prod_is_not_created`; вручную — `AISKRA_APP_ENV=prod uv run python -m aiskra.cli check-config` → код 1 и сообщение | ✅ | Пароль администратора: из списка известных, равен паролю демо-учёток, содержит логин, < 12 символов или < 3 видов символов из 4 |
| RF6-06 | `settings.py:prod_allow_http` (`AISKRA_PROD_ALLOW_HTTP`) — только cookie без `Secure`, предупреждение при каждом запуске; пароли и внешние модели не переопределяются | `unit/test_startup_checks.py::test_training_contour_without_tls_override` | ✅ | ADR-0015 — почему одно переопределение |
| RF6-07 | `settings.py:version` (`AISKRA_VERSION`, по умолчанию `unknown`); `backend/Dockerfile`: `ARG AISKRA_VERSION=unknown`, `ENV AISKRA_VERSION`; `docker-compose.yml`: `build.args`; `Makefile up` — короткий sha коммита; `main.py`: `app.state.started_at`, версия приложения в схеме API; `platform/health.py`: `env`, `version`, `started_at`. Фронт: `shared/api/system.ts:Health`, плашка «режим · версия» на `/admin/ai` | `integration/test_prod_mode.py::test_health_reports_env_version_and_start_time` | ✅ | |
| RF6-08 | [`docs/adr/0015-environment-modes.md`](../docs/adr/0015-environment-modes.md), строка в `docs/adr/README.md` | — | ✅ | |
| RF6-09 | см. §4 «D4»: `assessment/domain/validation.py:run_benchmark`; `tests/integration/conftest.py:make_settings` (`scheduler_enabled=False`); `tests/integration/test_psy.py::test_pause_and_sensitive_warning`; `tests/integration/test_teacher_feedback.py::test_save_edit_and_student_history` | `unit/test_validation.py::test_benchmark_skips_mutation_of_unchecked_criterion`; 20 прогонов подряд — §5 | ✅ | |
| RF6-10 | `tests/unit/test_startup_checks.py`, `tests/integration/test_prod_mode.py`; `test_security.py::test_prod_public_routes_outside_api` (вне `/api` в prod публичен только `/health`), старые prod-тесты — с `session_cookie_secure` | `make be-check` | ✅ | `PUBLIC` под `/api` не изменился |
| RF6-11 | эта спецификация; `docs/demo/Стенд_и_скринкаст.md` («Режимы окружения»); `.env.example`; `README.md` (быстрый запуск); AGENTS.md; `specs/0.1-architecture.md` (`/admin/ai`) | — | ✅ | |

## 4. Решения
- **Режимы** — таблица и обоснование в ADR-0015.
- **Проверка одна, вызывается дважды.** `check_startup` — в `create_app` (любой способ запуска API) и в `cli check-config` первым шагом контейнера. Так в prod слабый пароль администратора не попадёт в БД через `ensure-admin` раньше, чем запуск будет отклонён: `ensure-admin` создаёт администратора один раз и потом пароль не меняет.
- **Сообщение перечисляет все проблемы сразу**, чтобы не чинить их по одной за перезапуск. Секретов в нём нет, только имена переменных:
  ```
  Ошибка: Запуск в режиме prod (AISKRA_APP_ENV=prod) отклонён — небезопасные настройки:
    • [cookie_insecure] cookie сессии без флага Secure — задайте AISKRA_SESSION_COOKIE_SECURE=true и откройте вход по HTTPS (в docker compose это уже так). Учебный контур без TLS: AISKRA_PROD_ALLOW_HTTP=true
    • [db_password] пароль БД пустой или по умолчанию — задайте свой POSTGRES_PASSWORD в .env (его же docker compose подставит в AISKRA_DATABASE_URL)
  Исправьте .env и перезапустите. Для демонстрационного стенда — AISKRA_APP_ENV=demo (ADR-0015).
  ```
- **Явное разрешение внешних моделей** — та же переменная `AISKRA_AI_ALLOW_EXTERNAL`, которую `config/ai.openrouter.yaml` подставляет в `allow_external`. С ней конфиг и проверка согласованы. Если `allow_external: true` записан в YAML прямо, без переменной, prod не запустится.

### D4 — нестабильные тесты: что найдено и почему
**Как искали:**
- копия `main`;
- 20 полных прогонов подряд в обычном порядке;
- 20 прогонов в случайном порядке (`pytest-randomly`, seed 1001–1020);
- модуль `test_teacher_analytics.py` отдельно: 110 раз в обычном порядке и 20 раз в случайном;
- 8 модулей, которые генерируют сценарии, — под нагрузкой CPU (10 процессов-«печек», средняя загрузка машины больше 100);
- оценочный скрипт на 400 сгенерированных сценариях.

Причин нашлось четыре, все — общее состояние или случайность в тестах, а не ретраи:

1. **`test_teacher_analytics.py::test_validation_report` (основная, D4).**
   - **Что падало.** Тест ждёт, что бенчмарк мутаций находит все ошибки (`detection == 1`).
   - **Откуда случайность.** Сценарии занятия офлайн-генератор строит случайно: `random.Random(None)`, без seed.
   - **Несогласованное правило.** Одно правило бенчмарка расходилось с правилом оценки. По п. 3.5 критерий «Описание» требует только те ключевые факты, которые заявитель произнёс. Поэтому у типа «Горит мцк» (ключевые слова «открытое пламя» в речи заявителя не звучат) критерий не проверяется вовсе. Бенчмарк же применял к такому сценарию мутацию «пустое описание» и считал её пропуском. Получалось `detection = 0,975`.
   - **Как часто.** Так выходит примерно у 1 % сценариев группы 1, это 1–2 % прогонов при двух сценариях в занятии. Воспроизведено: 1 падение из 80 запусков модуля в обычном порядке.
   - **Случайный порядок.** Падения чаще: `test_scenario_edit_runs_grammar_check` переписывает легенду утверждённого сценария («Горит балкон.»), и из речи пропадают ключевые слова.
   - **Исправление** — в `run_benchmark`: мутация в критерий, который у этого сценария не проверяется, не считается случаем бенчмарка. Это исправление продукта: на экране «Достоверность» такие «пропуски» тоже занижали чувствительность.
2. **Фоновая ежедневная резервная копия работала в тестах.**
   - **Что не так.** В `make_settings` не было `scheduler_enabled=False`, хотя комментарий в `settings.py` говорил «в тестах выключается».
   - **Чем мешает.** Приложение, которое прожило больше 60 с (модульные фикстуры под нагрузкой), в случайный момент:
     - выгружает всю базу SQLite, конкурируя с запросами теста;
     - пишет в аудит «Создана резервная копия».

     После 03:00 МСК это происходит всегда. Подтверждено отдельным тестом: через 66 с в аудите появляется `system.backup_created`.
   - **Исправление.** Планировщик в тестах выключен. Логику копии проверяет `unit/test_daily_backup.py`.
3. **`test_psy.py`: случайный выбор из общего банка.**
   - **Повтор вместо детерминизма.** `test_pause_and_sensitive_warning` до 12 раз звонил, пока случайный выбор не попадёт на нужный сценарий. В обычном порядке промахивался примерно в 1 % случаев.
   - **Утечка в соседний тест.** Закреплённый кризисный профиль оставался в общей группе 1. При другом порядке он попадал в звонок `test_session_with_modifier_call_and_block`, и тот падал: `voice` — `None`.
   - **Исправление.** Сценарий теста — в своей группе классификатора (2): звонок детерминирован, повтор убран.
4. **`test_teacher_feedback.py::test_save_edit_and_student_history`.**
   - **Что не так.** Тест считал все события «Отзыв сохранён» в общей базе модуля, а соседний тест тоже сохраняет отзыв. В случайном порядке получалось 3 вместо 2.
   - **Исправление.** Считаются только события, появившиеся в самом тесте.

## 5. Критерии приёмки
- [x] В prod нет демо-входа, `/dev` и анонимного Swagger: автотесты `test_prod_mode.py`, `test_security.py`.
- [x] Запуск prod с небезопасными настройками отклоняется сообщением с кодом проблемы и подсказкой: `test_startup_checks.py`, `test_prod_mode.py::test_unsafe_prod_is_not_created`.
- [x] `/health` отдаёт `env`, `version`, `started_at`.
- [x] D4. До исправления — 12 из 20 прогонов в случайном порядке с падениями: `test_teacher_feedback` 7 раз, `test_validation_report` 5 раз, `test_psy` 4 раза. В обычном порядке — 1 падение `test_validation_report` из 80 запусков модуля. После исправления без падений:
  - 20 из 20 прогонов подряд в обычном порядке;
  - 20 из 20 в случайном порядке;
  - 18 из 20 под нагрузкой CPU — цикл остановлен по времени, упавших нет.
- [x] `make be-check`, `make fe-build` зелёные.

## 6. Отклонения, долги, открытые вопросы
- **`fake` в `ai.default_provider` в prod не отклоняет запуск** (техспека 6.3 этого требует). Офлайн-режим — штатный режим контура по ТЗ. Запуск пишет в лог «модели не подключены». Обоснование — ADR-0015.
- **`docker compose up` с `.env.example` как есть в prod не запустится:** пароль БД `aiskra`. Это намеренно. CI и smoke (F6.4) должны задавать `AISKRA_APP_ENV=demo` или свои пароли.
- **Администратор, созданный раньше со слабым паролем, не обнаруживается.** Проверяется только переменная окружения.
- **Swagger UI в изолированном контуре** — скрипты страницы `/docs` FastAPI берёт с CDN. Без интернета работает только `/openapi.json`.
- **Пояснительная записка** (`docs/delivery/Пояснительная_записка.md`, «`/docs` публикуется сервером») не пересобрана: нужен LibreOffice. Уточнение «в prod — только администратору» — при следующей сборке.
