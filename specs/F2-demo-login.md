# F2 — Демо-учётки на странице входа

- **Приоритет:** P0 · **Статус:** 🟡 реализовано, кроме кнопки «Сбросить демо-данные» (RF2-06, см. §6)
- **Ветка:** `feat/F2-demo-login` · **Решения:** [ADR-0015](../docs/adr/0015-environment-modes.md) «Режимы окружения prod/demo/dev» (здесь — только сам режим `AISKRA_APP_ENV`, остальное — [F6.3](F6-prod-modes.md)), [ADR-0010](../docs/adr/0010-auth-rbac-audit.md) (вход, сессии, аудит)
- **Зависит от:** F6.3 (режимы окружения — минимальная часть сделана здесь) · **Опирается на:** [0.3](0.3-auth-rbac-audit.md), [6.2](6.2-security.md), [M6](M6-e2e.md) (`demo-seed`)

## 1. Пункт плана
> **F2. Демо-учётки на странице входа — P0.** Эксперт открывает стенд и входит в любую роль одним кликом, без README.
>
> Источник — [техспека бэклога финала](../docs/brief/07_Бэклог_финала_техспека.md), раздел F2; режимы окружения — раздел F6.3.

## 2. Требования
| ID | Требование | Источник |
|---|---|---|
| RF2-01 | Режим окружения `AISKRA_APP_ENV = prod \| demo \| dev`. Панель учёток — только в `demo` и `dev`. В `prod` эндпоинты отвечают 404, панели нет | техспека F2, F6.3 |
| RF2-02 | `GET /api/v1/auth/demo-accounts` — публичный, только demo/dev. Логин, роль, ФИО, «что посмотреть», номер АРМ по умолчанию. **Паролей не отдаёт** | техспека F2 |
| RF2-03 | `POST /api/v1/auth/demo-login {login}` — вход без пароля только для учёток `DEMO_USERS` (`demo_seed.py`), только demo/dev. Администратор не входит. Событие аудита `auth.demo_login` | техспека F2 |
| RF2-04 | `AISKRA_DEMO_SHOW_PASSWORD=true` → пароль демо-учёток виден на странице текстом. По умолчанию выключено | техспека F2 |
| RF2-05 | `LoginPage.tsx`: лента «Демонстрационный стенд, данные синтетические» над формой; блок «Демо-учётки» под формой — карточки ролей (иконка, роль, ФИО, 1–2 строки «что посмотреть», кнопка «Войти») | техспека F2 |
| RF2-06 | Первый вход демо-учётки не сбрасывает чужой прогресс подсказок. Кнопка «Сбросить демо-данные» — только у администратора (demo-seed и demo-history) | техспека F2 |
| RF2-07 | Ограничение частоты `demo-login`: не чаще 10 в минуту с одного IP | техспека F2 |
| RF2-08 | `test_security.py`: новые публичные маршруты осознанно в `PUBLIC` и проверены на 404 в `prod` | техспека F2, AGENTS.md «Безопасность» |

## 3. Трассировка
База путей бэкенда — `backend/src/aiskra/`, тестов — `backend/tests/`.

| ID | Реализация | Проверка | Статус | Примечание |
|---|---|---|---|---|
| RF2-01 | `platform/settings.py`: `app_env: Literal["prod","demo","dev"]` (регистр и пробелы нормализуются, иное значение — ошибка запуска), `demo_enabled`; `main.py`: `demo_router` подключается только при `demo_enabled`; `/health` отдаёт `env`. `docker-compose.yml`: `AISKRA_APP_ENV: ${AISKRA_APP_ENV:-prod}`; `.env.example` — `prod` с пояснением. Фронт: блок и лента — только если `demo-accounts` ответил списком | `unit/test_demo_login.py::test_app_env_values`; `integration/test_demo_login.py::test_prod_has_no_demo_routes` (404, нет в OpenAPI, `/health` → `prod`), `::test_dev_has_demo_routes` | ✅ | Settings по умолчанию — `dev` (локальная разработка и тесты); docker compose без переменной — `prod` |
| RF2-02 | `identity/application/queries/demo_accounts.py` (`ListDemoAccountsHandler`: только учётки из списка, которые есть в базе, активны и не администраторы), порт `UserReader.by_logins` (`infrastructure/reader.py`), `api/router.py:demo_accounts`, схема `DemoAccountsOut` | `integration/test_demo_login.py::test_accounts_listed_without_passwords`, `::test_blocked_account_hidden_and_cannot_enter`; `unit/test_demo_login.py::test_list_shows_existing_active_non_admin_without_password` | ✅ | |
| RF2-03 | `identity/application/commands/demo_login.py` (`DemoLoginHandler` → `LoginHandler.open_session` с `AuditEvent.DEMO_LOGIN`, номер АРМ из `DemoUser.arm_number`), `ports/demo.py:DemoPolicy`, `bootstrap.py:build_demo_policy` (из `demo_seed.DEMO_USERS`, админ исключён), `shared/audit.py:DEMO_LOGIN` + название | `integration/test_demo_login.py::test_demo_login_opens_regular_session_and_is_audited`, `::test_only_demo_accounts_can_enter[admin\|student\|ghost\|op2]`, `::test_bad_body_is_422`, `::test_password_lockout_does_not_close_demo_login`; `unit/test_demo_login.py::test_demo_login_*`, `::test_only_existing_non_admin_demo_accounts`, `::test_blocked_account_refused_and_audited` | ✅ | Чужой логин → 404 `demo_account_not_found`, заблокированная администратором учётка → 401 `account_blocked` + `auth.login_failed` в аудит |
| RF2-04 | `settings.py`: `demo_password` (`AISKRA_DEMO_PASSWORD`), `demo_show_password` (`AISKRA_DEMO_SHOW_PASSWORD`, по умолчанию `false`); пароль попадает в `DemoPolicy` только при флаге и режиме demo/dev; страница показывает его в блоке, только если пришёл | `integration/test_demo_login.py::test_password_shown_only_with_flag`, `::test_accounts_listed_without_passwords`; `unit/test_demo_login.py::test_demo_policy_from_settings` (в `repr` пароля нет) | ✅ | |
| RF2-05 | `frontend/src/pages/LoginPage.tsx` (`DemoPanel`), `frontend/src/shared/api/auth.ts` (`useDemoAccounts` — 404 → `null`, `useDemoLogin`), стили `arm-login__side`, `arm-login__ribbon`, `arm-demo*` в `packages/ui-kit/css/arm.css` (только токены ui-kit), иконки ui-kit `school` / `headset` / `phone` | `make fe-build`; вручную (demo, SQLite): 1024 px и 375 px — горизонтальной прокрутки нет, «Войти» у преподавателя → `/teacher`, у `op1` → `/arm/112/journal`, сессия с АРМ 101 | ✅ | После демо-входа — тот же переход, что после обычного (`homeFor`, возврат на `from`) |
| RF2-06 | Демо-вход не трогает `users.onboarding`, сессии других экспертов под той же учёткой не отзываются | `integration/test_demo_login.py::test_demo_login_keeps_onboarding_progress` | 🟡 | Кнопки «Сбросить демо-данные» нет — §6 |
| RF2-07 | `platform/ratelimit.py:SlidingWindowThrottle.hit` (считается каждый запрос), отдельный экземпляр `limit=10, window_s=60` в `bootstrap.py`, порт `ports/demo.py:RequestLimit`; проверка до обработки запроса → 429 `too_many_requests` | `integration/test_demo_login.py::test_demo_login_rate_limited_per_ip`; `unit/test_demo_login.py::test_hit_counts_every_request` | ✅ | Лимит входа по паролю (20 неудач за 15 мин) не затронут |
| RF2-08 | `tests/integration/test_security.py`: `PUBLIC` + `DEMO_ONLY`; `test_rbac.py` берёт тот же `PUBLIC` | `integration/test_security.py::test_every_api_route_requires_session`, `::test_demo_public_routes_absent_in_prod` | ✅ | |

## 4. Решения
- **Маршруты в prod отсутствуют, а не закрыты.** `demo_router` подключается в `main.py` только в demo/dev: в prod их нет ни в API, ни в OpenAPI. Обработчики дополнительно проверяют `DemoPolicy.enabled` — защита на случай ошибки подключения.
- **Список учёток — из `DEMO_USERS`** (`demo_seed.py`, поля `title`, `hint`, `arm_number`). Модуль identity о нём не знает: composition root (`bootstrap.build_demo_policy`) собирает `DemoPolicy`. Импорт `demo_seed` — внутри функции: сам `demo_seed` импортирует `bootstrap`.
- **Учётка показывается, только если она есть в базе, активна и не администратор.** До `demo-seed` блок пустой, и страница выглядит как обычно.
- **Временная блокировка неверными паролями демо-вход не закрывает.** На публичном стенде её может включить кто угодно, и учётка перестала бы работать для всех. Блокировка администратором закрывает.
- **Сессия — обычная** (`LoginHandler.open_session`): те же TTL, cookie, `register_login`, запись в аудит, только событие `auth.demo_login`.
- **Лимит частоты** — тот же `SlidingWindowThrottle`, что у входа по паролю, но отдельный экземпляр, и считается каждый запрос (`hit`), а не только неудачный.

## 5. Критерии приёмки
- [x] В режиме demo — вход в каждую из 5 ролей одним кликом (учётки `teacher`, `op1`, `op2`, `dds1`, `dds2`).
- [x] В prod — эндпоинтов нет (404), панели нет; тест это проверяет.
- [x] Пароли не уходят в API (без флага) и не видны в коде страницы.
- [x] Новые публичные маршруты — в `PUBLIC` `test_security.py`.

## 6. Отклонения, долги, открытые вопросы
- **Кнопка «Сбросить демо-данные» (RF2-06) не сделана.** `demo-seed` и `tools/demo_history.py` сейчас — команды CLI с паролем из окружения, а `demo_history` вообще не входит в пакет. Кнопке нужен админский эндпоинт с фоновым запуском и правом `system.manage`. Это отдельная задача. Пока данные сбрасывают `make demo-seed-docker && make demo-history-docker`.
- **Стенд нужно перевести в `AISKRA_APP_ENV=demo`.** В docker compose по умолчанию теперь `prod`. На публичном стенде в `.env` должно быть `AISKRA_APP_ENV=demo`, иначе блока демо-учёток не будет.
- **Пароль из README удалён, но остался в истории git** (D7 в техспеке): пароль демо-учёток на стенде нужно сменить (`admin` → «Пользователи» → «Новый пароль»).
- Остальная часть F6.3 (fail-fast проверки prod, Swagger только администратору, версия в `/health`) — сделана в [F6.3](F6-prod-modes.md), решение — [ADR-0015](../docs/adr/0015-environment-modes.md).
