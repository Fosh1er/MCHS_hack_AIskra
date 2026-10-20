# AGENTS.md — правила для кодинговых агентов (и людей)

**АИскра** — учебный тренажёр оператора 112 и диспетчера ДДС с ИИ. Хакатон ЛЦТ-2026, задача №9 (ДГОЧСиПБ Москвы, ГБУ «Система 112»).
Сдача: **29.09.2026 23:59 МСК**, финальная доработка — до **20.10.2026 23:59 МСК**. После неё — стоп-код: никаких коммитов в сданные ветки.

Этот файл короткий. Подробнее:
- **план** — [docs/brief/02_План_работ.md](docs/brief/02_План_работ.md) (источник истины по объёму работ);
- **требования** — [docs/brief/01_Консолидированные_требования.md](docs/brief/01_Консолидированные_требования.md);
- **решения** — [docs/adr/](docs/adr/README.md);
- **правила** — [docs/rules/](docs/rules/);
- **архитектура** — [docs/architecture/overview.md](docs/architecture/overview.md);
- **спецификации пунктов плана с трассировкой «требование → код → тест»** — [specs/](specs/README.md).

## Карта репозитория
```
backend/            FastAPI + SQLAlchemy 2 async + PostgreSQL (uv, Python 3.12)
  src/aiskra/
    shared/         ядро: Entity, ошибки, Command/Query, di.provider_stub, кеш, security (роли и права),
                    audit (порт журнала), web (FastAPI: CurrentPrincipal, require), text (ключи поиска)
    ai/             порты LLM/STT/TTS, ModelRouter, конфиг, adapters/ (openai_compatible, fake, caching)
    platform/       настройки, БД, health, контейнер Services
    modules/<m>/    domain · application/{commands,queries,ports} · infrastructure · api
    bootstrap.py    composition root: порт → адаптер, wire() заглушек
    main.py         FastAPI-приложение
  migrations/       Alembic
  tests/            unit/ (без БД) · integration/ (TestClient + SQLite)
frontend/           React 18 + Vite + TS + TanStack Query (страницы, api-хуки)
packages/ui-kit/    библиотека стилей и компонентов АРМ-112/ДДС (копия интерфейса заказчика)
config/ai.yaml      назначение моделей на ИИ-задачи (по умолчанию офлайн: fake)
data/               исходные данные заказчика и нормализованные справочники
specs/              пункт плана → требования → реализация → тесты (трассировка)
docs/               brief · adr · rules · architecture
```

## Команды
```bash
make be-install && make be-check     # uv sync; ruff + mypy --strict + import-linter + pytest
make fe-install && make fe-build     # npm install; tsc + vite build
docker compose up --build            # db + backend (:8000/docs) + frontend (:8080)
cd backend && uv run alembic upgrade head && uv run python -m aiskra.cli import-dictionaries   # схема + справочники
cd backend && uv run python -m aiskra.cli import-addresses   # адресный справочник и границы районов (п. 1.2)
cd backend && uv run python -m aiskra.cli create-user --login admin --full-name "…" --role admin   # пользователь
make e2e                             # F6.5: сквозные сценарии в браузере, стенд поднимается сам (раздел «E2E»)
tools/stand/stand up [--local]       # 7.4: стенд на своём компьютере под доменом (Caddy + Let's Encrypt), docs/demo/Стенд_на_своём_компьютере.md
```
**Перед каждым коммитом зелёными должны быть `make be-check` и `make fe-build`.**

## Архитектура в 10 правилах
1. **Модульный монолит.** Модули: `system`, `identity`, `dictionaries`, `incidents`, `training`, `assessment`, `audit`. Импорт модуль→модуль запрещён (import-linter). Если связь нужна — ADR и явное исключение.
2. **Слои внутри модуля:** `api | infrastructure → application → domain`. `domain` — чистый Python: без FastAPI, SQLAlchemy, httpx и pydantic.
3. **CQRS-lite (ADR-0002).**
   - Команда (`application/commands/*.py`): dataclass `Command` + обработчик, меняет состояние через репозиторий и UoW.
   - Запрос (`application/queries/*.py`): `Query` + DTO + обработчик/порт чтения, **ничего не меняет**.
   - Шин нет, обработчик вызывается из API напрямую.
4. **Порты и адаптеры (ADR-0003).**
   - Внешний мир (БД-репозитории, модели, речь, часы) — только через `Protocol` в `application/ports` или `aiskra.ai.ports`.
   - Адаптеры живут в `infrastructure/` или `aiskra/ai/adapters/`.
5. **DI без фреймворка (ADR-0004).** В `api/deps.py` — `provider_stub(...)`. В `bootstrap.wire()` — `app.dependency_overrides[stub] = factory`. API не импортирует `bootstrap` и адаптеры.
6. **ИИ только через `ModelRouter.for_task(AITask.X)`.** Никаких прямых HTTP-вызовов моделей и жёстко прописанных URL. Модель задачи задаётся в `config/ai.yaml`.
7. **Кеш ИИ — декоратор (ADR-0006).** Режимы `exact` / `task` / `off` задаются в конфиге задачи. Детерминированные задачи (оценка) — `exact`, реплики актёров — `task` со `scope`, генерация — `off`.
8. **Ошибки — исключения из `aiskra.shared.errors`.** HTTP-коды назначаются только в `main.py` (`DomainError` 422, `NotFoundError` 404, `PermissionDeniedError` 403, `ExternalServiceError` 503). У `ExternalServiceError` `message` — подробности для журнала (код ответа, адрес), пользователю уходит `public_message` без них; своя фраза — `public=`.
9. **ORM-модели** — в `modules/<m>/infrastructure/models.py`, регистрируются в `platform/models_registry.py`. Схема меняется **только миграцией Alembic**.
10. **Язык.** Интерфейс, сообщения об ошибках, докстринги и документация — по-русски. Идентификаторы в коде — по-английски.

## Безопасность (п. 0.3, ADR-0010) — обязательно для каждого эндпоинта
- **Всё под `/api/v1` требует входа по умолчанию** (подключение роутеров в `main.py`). Публичен только `POST /auth/login` (и демо-вход F2 — только в режимах demo и dev).
- **Право, а не роль:**
  - `Depends(require(Permission.X))` на роутере или эндпоинте;
  - нужен сам пользователь — `actor: Annotated[Principal, Depends(require(...))]` или `CurrentPrincipal`.
  - Новое право — значение в `shared/security.py:Permission` и строка в `ROLE_PERMISSIONS`, плюс тест матрицы.
- **Значимое действие → аудит.** Обработчик команды получает `AuditRecorder` в `__init__`, пишет `AuditEntry(event=AuditEvent.X, actor=cmd.actor, meta=cmd.meta, …)` до `uow.commit()`. Новое событие — значение в `shared/audit.py:AuditEvent` и название в `AUDIT_EVENT_TITLES`.
- **Команда от имени пользователя** несёт `actor: Principal` и `meta: RequestMeta` (в API — зависимость `Meta` из `shared/web.py`).
- **Поиск по тексту** — только по ключам `shared/text.py:search_key`, сохранённым при записи. Не используйте `func.lower()`: он зависит от локали PostgreSQL.
- **Проверено автотестом:** любой маршрут `/api/v1` без сессии отвечает 401 (`test_security.py`). Публичный маршрут — только осознанно, с добавлением в `PUBLIC` теста.
- **Режимы окружения** — `AISKRA_APP_ENV = prod | demo | dev` (`settings.demo_enabled`, ADR-0015; docker compose по умолчанию — `prod`). Демо-вход без пароля (F2: `GET /auth/demo-accounts`, `POST /auth/demo-login`, `identity/api/router.py:demo_router`) подключается только в demo/dev, в prod маршрутов нет (404). Входят только учётки `demo_seed.py:DEMO_USERS`, админа там быть не должно; пароль в API — по умолчанию (рекомендации экспертов), скрыть — `AISKRA_DEMO_SHOW_PASSWORD=false`. **В prod** демо-учётки и пароль тоже показываются, если задан `AISKRA_DEMO_PASSWORD` (рекомендации экспертов финала); контур без демо-учёток — `AISKRA_DEMO_IN_PROD=false`.
- **prod (F6.3, ADR-0015):**
  - запуск отклоняется при небезопасных настройках — `platform/startup_checks.py:check_startup` (в `create_app` и `cli check-config`, коды `cookie_insecure`, `db_password`, `admin_password`, `external_ai`; переопределение одно — `AISKRA_PROD_ALLOW_HTTP`); в demo/dev — предупреждения;
  - Swagger и `/openapi.json` — только `system.manage` (`platform/api_docs.py`); маршрутов `/dev` нет, «ИИ-модели» — `/admin/ai`;
  - `/health` — `env`, `version` (`AISKRA_VERSION`, build-arg образа), `started_at`. Новая проверка настроек — код в `find_problems` и тест в `unit/test_startup_checks.py`;
  - интеграционные тесты prod: `session_cookie_secure=True`, иначе `create_app` откажет.
- **Заголовки безопасности** ставит `platform/security_headers.py`; ответы API — `no-store`. Непредвиденная ошибка → единый 500 без подробностей.
- **Журнал аудита** не редактируется; удаление — только очистка старше срока (не меньше 183 дней, `PurgeAudit`).
- **Интеграционные тесты:** фикстуры `admin`, `client`, `app_client` и функция `login(client, "student")` в `tests/integration/conftest.py`. Пользователи трёх ролей создаются автоматически.

## Справочники (п. 0.2) — что уже есть
- **Типы происшествий:** `dict_incident_types` (1281, дерево признаков 1→2→3), `dict_card_types` (51 тип «что случилось?»).
- **Матрица служб:** `dict_routing` + `dict_service_columns` (кто получает карточку при каких признаках).
- **Службы:** `dict_services` (221, телефоны синтетические). **Территория:** `dict_okrugs`, `dict_districts`.
- **Перечисления:** `dict_enums` (статусы, признаки, каналы).
- **Структура карточки 112:** `modules/incidents/domain/card.py:IncidentCardData`.
- **API:** `/api/v1/dictionaries/*` (см. [спецификацию 0.2](specs/0.2-data-model.md) §6). Таблицы остальных модулей уже созданы миграцией 0002 — используйте их, а не создавайте новые.

## Карточка 112 (п. 1.1) — что уже есть
- **Экран:** `frontend/src/pages/card112/` — `Card112Page.tsx` (сборка, таймер, сохранение, горячие клавиши), `state.ts` (редьюсер и правила), блоки по зонам. Маршруты `/arm/112` (Insert — новая карточка) и `/arm/112/:id`.
- **API:** `POST /api/v1/incidents/cards` → номер; `POST /cards/{id}/save` → «Зарегистрирована» или «Завершена» (пустая); `GET /cards/{id}`.
- **Автоподбор служб:** `GET /api/v1/dictionaries/services/resolve?incident_type=…&flag=…&district=…` — основа п. 1.5.
- **Правила сохранения** — `modules/incidents/domain/incident.py:missing_for_save` (сервер) и `state.ts:missingFields` (клиент). Меняете одно — меняйте и другое.

## Адрес и карта (п. 1.2) — что уже есть
- **Данные:** `data/dictionaries/addresses.csv.gz` и `districts_geo.json` из OpenStreetMap, генератор `data/tools/build_addresses.py`. Таблицы `dict_streets`, `dict_addresses`, `dict_district_shapes`; импорт — отдельная команда `import-addresses` (в тестах других модулей адресов нет).
- **API:** `GET /api/v1/dictionaries/addresses/suggest?q=`, `/addresses/reverse?lat=&lon=`, `/addresses/houses?min_lat=…`, `/territory/shapes`. Разбор строки и геометрия — `modules/dictionaries/domain/address.py`.
- **Фронт:** подсказки в `pages/card112/AddressBlock.tsx`, окно карты `AddressMap.tsx` (Leaflet без тайлов). Esc в окне карты закрывает карту — слушатель в фазе захвата.

## Журнал и сохранённая карточка (п. 1.3) — что уже есть
- **Журнал:** `frontend/src/pages/journal/JournalPage.tsx`, маршрут `/arm/112/journal` — стартовый экран обучающегося (`auth.ts:homeFor`). API `GET /api/v1/incidents/journal` (свои — обучающемуся, все — преподавателю). Сетка `.arm-j112` в ui-kit.
- **Просмотр сохранённой карточки:** `pages/card112/CardViewer.tsx` (Card112Page показывает его для любого статуса, кроме `draft`). Действия — `shared/api/incidents.ts:useCardActions`: `worked`, `checked`, `returned`, `flags`, `append`, `workout`; «Просмотр карточки» в аудит — `markCardViewed` один раз при открытии.
- **Статусы:** хранимый `status` и вычисляемый `display_status` (`not_notified`). Подписи — `incidents.ts:CARD_STATUS`, `SERVICE_STATUS`.
- **Дополняемые поля** — `domain/incident.py:APPENDABLE_FIELDS` (сервер) и `CardViewer.tsx:APPENDABLE` (клиент). Меняете одно — меняйте и другое.

## Повторные обращения и связи (п. 1.6, ТЗ 4.6) — что уже есть
- **Связь** — `incident_cards.main_card_id` (миграция 0021), одноуровневая: подчинённая указывает на главную. Правила — `incidents/domain/links.py` (`phone_key` — последние 10 цифр, `address_key`, `link_target`), порт `CardLinks` → `infrastructure/links.py`.
- **API:** `GET /incidents/matches?phone=…&street=&house=&exclude=` (свои карточки за 24 ч), `POST /incidents/cards/{id}/link {main_id | null}` (аудит `card.linked` / `card.unlinked`), `GET /cards/{id}/links`; журнал — `JournalRow.linked`.
- **Фронт:** `pages/card112/CardLinks.tsx` — `MatchesDialog` («Есть карточка с заявителем по этому номеру», сам — только при повторном звонке: сценарии банка повторяются вместе с номером) и `LinksDialog` (скрепка в нижней панели); «совпадение» — `AddressBlock.onMatch`; строки — `JournalPage.tsx:Row`, `JournalHead`.
- **Учебный повторный звонок** — настройка занятия `repeat_share` (%, по умолчанию 0), `StartIncomingCallHandler._repeat_call`, `training_calls.repeat_of`, `CallView.repeat_of`; оценка — критерий `repeat_link` (вес 3, критический), см. [спецификацию 1.6](specs/1.6-repeat-calls.md).

## АРМ ДДС (п. 2.1, 2.2) — что уже есть
- **Экраны:** `frontend/src/pages/dds/` — `DdsSelectPage` (`/arm/dds`, выбор службы), `DdsJournalPage` (`/arm/dds/:service`, реестр с таймерами), `DdsCardPage` (`/arm/dds/:service/:id` → `CardViewer` с `dds`).
- **API:** `GET /api/v1/incidents/dds/{service}/journal`, `GET …/cards/{id}` (с `next_statuses`), `POST …/cards/{id}/received`, `POST …/cards/{id}/status`.
- **Кто что видит (ТЗ 2.7, 2.8)** — `application/queries/dds.py:dds_scope`: диспетчеру на идущем занятии — только его служба (порт `DdsPosts`, адаптер `integration/session_sources.py:TrainingDdsPosts`) и карточки этого занятия (`ensure_in_scope`, `DdsFilter.session_ids`); вне занятия — свободная практика: любая служба, только карточки вне занятий (`session_ids = [None]`, `infrastructure/dds.py:in_sessions`); преподавателю — все. Новый маршрут ДДС — через `dds_scope`. В тестах ДДС — занятие `test_journal.py:start_lesson`.
- **Самостоятельная тренировка (рекомендация экспертов п. 10)** — `POST /training/self-training/dds {service_code}` (`training.participate`, `commands/self_training.py:RequestDdsSelfCardHandler`, правила выбора — `domain/self_training.py`): вне занятия обучающийся сам берёт учебную карточку — утверждённый сценарий банка, где служба есть в эталоне (случайно, зерно — пользователь и время, недавние не повторяются), иначе генерация на лету (без модели — офлайн, сценарий — черновиком на проверку). Карточка системная (`origin = system`), вне занятия, автор — сам обучающийся (порт `SelfTrainingCards`, адаптер `integration/session_sources.py:IncidentSelfTrainingCards`); видит её только он и преподаватель (`in_sessions(…, viewer_id)`, `ensure_in_scope(…, viewer_id)`), в журнал 112 и поиск совпадений обучающегося такие карточки не попадают. Предел — `MAX_SELF_WAITING = 3` ожидающих решения (422 `self_queue_full`), на занятии — 422 `in_session`, аудит `sessions.dds_self_card`. Фронт: кнопка «учебная карточка» в `DdsJournalPage` (только вне занятия), `DdsCardView.self_training` — признак учебной карточки; рекомендации по слабым критериям — `details.recommendations` каждой оценки (`recommendations.py:recommend`) и кабинет `/student`.
- **Правила статусов** — `modules/incidents/domain/dds.py` (`NEXT`, `check_transition`). Очередь ДДС = `card_services` сохранённых карточек; `dds_queue_items` — для потока по расписанию (4.2).
- **Бригады (п. 5.5)** — справочник `dict_brigades` из `data/dictionaries/brigades.yaml` (импорт вместе со справочниками, ключ «<служба>:<позывной>»); `GET /incidents/dds/{service}/brigades`, выбор — `ServiceStatusIn.brigades` → `dds.py:check_brigades`; состав — `card_services.brigades`. Бригада занята, пока её карточка не в окончательном статусе.
- **Телефонная книга ДДС (п. 2.3, рекомендация экспертов)** — абоненты IP-телефона службы задаёт преподаватель: до 10 записей «должность + ФИО (синтетическое) + условный номер», должности — `training/domain/phonebook.py:ContactRole` (руководитель организации, начальник отдела реагирования, начальник и специалист аварийной бригады, «заявитель — номер из карточки»). Таблица `dds_phonebooks` (миграция 0022, одна строка на службу, записи JSON), правила — `validate_entries` (≤10, номер уникален по цифрам). API `GET /training/dds-phonebook/{service}` (диспетчер, преподаватель), `PUT …` — заменяет список целиком (`lessons.conduct`, аудит `dds.phonebook_saved`); экран `/teacher/dds-phonebook` (`pages/teacher/DdsPhonebookPage.tsx`).
  - Звонок по номеру — `StartDdsCall.number` → `resolve_number`: абонент книги — `party=brigade` (тот же агент старшего группы, должность — в `training_calls.contact` и в промпте), номер заявителя из карточки — `party=applicant`, только если в книге есть «заявитель»; иначе 422 `number_not_served` «Номер не обслуживается», звонок не создаётся. Клавиша «заявитель» без записи в книге — 422 `applicant_not_in_book`.
  - **Книги нет или она пуста — всё как раньше** (клавиши «старший группы», «заявитель», службы; `number` не принимается). Входящий доклад старшего группы от книги не зависит. Демо-книги S101/S103 — `demo_seed.py:DEMO_PHONEBOOKS` (e2e `test_dds.py` звонит по ним).

## Сценарии, ИИ-собеседники, звонки (п. 3.2, 3.3, 1.4, 2.3) — что уже есть
- **Модуль `training`:** `domain/scenario.py` (легенда + эталоны, офлайн-легенда), `domain/actors.py` (офлайн-агенты), `domain/call.py`; `application/actors.py` (агенты поверх `ModelRouter`, при `fake` или ошибке модели — офлайн), `commands/scenarios.py`, `commands/calls.py`.
- **Промпты:** `aiskra/ai/prompts/<task>/v1.md` (`scenario_generation`, `applicant_actor`, `brigade_actor`, `service_actor`), загрузка — `aiskra.ai.prompts.load_prompt`.
- **Связь модулей:** `aiskra/integration/training_sources.py` реализует порты `training` через `dictionaries` и `incidents` (модули друг друга не импортируют).
- **API:** `/api/v1/training/scenarios…`, `/training/calls/incoming`, `/calls/dds`, `/calls/{id}/answer|replicas|end`, `/training/cards/{id}/calls`. CLI `generate-scenarios --count N`.
- **Фронт:** входящий вызов — `pages/journal/JournalPage.tsx`; панель разговора — `shared/ui/CallPanel.tsx`; софтфон ДДС — `pages/dds/DdsSoftphone.tsx` (свёрнут по умолчанию — зелёный кружок `.ipphone-fab`, кнопка «IP-телефон», над панелью служб; при входящем докладе пульсирует; e2e нажимает его перед набором).

## Эмоции и голос ИИ-собеседника (п. 3.6, этапы V1–V4) — что уже есть
- **Состояние** — `training/domain/tone.py:CallerTone`: эмоция, напряжение, доверие, готовность отвечать (0–10). Начальное — `tone_for_legend` (сложность легенды, группа — первые цифры кода классификатора). Хранится в `training_calls.tone`, снимок у каждой реплики заявителя — `training_call_messages.tone` (миграция 0015).
- **Правила** — `CallerTone.react`: словари `CALMING` / `INVALIDATING` / `PRESSURE` + вопрос по новой теме (`topic_of`). Категория — раз на реплику, успокаивающая фраза — раз за звонок, успокоение — не больше 6. Меняете словари — поправьте таблицу 7.2 в `specs/3.6-emotional-voice.md` и `unit/test_caller_tone.py`.
- **Модель** получает состояние в промпте `applicant_actor/v2.md` (версия — `prompt_version` задачи в `config/ai*.yaml`), кеш делится по полосе напряжения; **без модели** ответ окрашивает `color_reply` — только слова вокруг фактов, факты легенды не меняются. Состояние меняют только правила, не модель.
- **API:** `ReplicaOut.tone`, `message_id`; `GET /training/calls/{id}` — `tone` звонка и у реплик. **Фронт:** `CallPanel.tsx:prosody` — темп, высота, громкость озвучки браузером; подпись «Заявитель · <эмоция>».
- **Серверный синтез (V2)** — `ai/adapters/speech.py:OpenAICompatibleTTS` за `TTSPort` (`/audio/speech`), конфиг `tts` (`TTSConfig`, переменные `TTS_*`). По умолчанию `fake` — озвучивает браузер. Эмоция уходит **параметром провайдера** (`style: google|openai`), текст реплики чистый; `none` — только темп (Piper). Подача — `domain/tone.py:speech_style`, `speech_speed`.
- **Резервные модели речи (F3)** — `tts.fallback` (модель, голос, формат) и `stt.fallback_model` в конфиге: `FallbackTTS` / `FallbackSTT` (`ai/adapters/speech.py`) берут резервную, если основная ответила ошибкой. Эмоции в голосе — по документации моделей: звуки и волнение реплики (`VoiceProfile.sounds`/`agitation`, домен — `training/domain/voice_cues.py`) адаптер размечает под модель (`ai/adapters/speech_markup.py`): Gemini — теги `<sob>`, `<cough>` в тексте, движок без стиля (MAI через OpenRouter, Piper) — восклицаниями. Текст реплики в звонке не меняется. Выбор моделей демо-стенда — шапка `config/ai.openrouter.yaml`, спецификация `specs/F3-models.md`.
- **Звук реплики** — `GET /training/calls/{id}/messages/{mid}/audio` (`application/speech.py:ReplicaAudioHandler`, права — `call_visible`); роль голоса — `applicant_female|male|applicant|brigade|service`, имя голоса провайдера — `tts.voices`. Кеш — `CachingTTS` с лимитом в байтах (`cache_mb`), не общий `CachePort`. Фронт — `CallPanel.play`: `<audio>` по адресу сайта (не `blob:` — CSP), при ошибке — голос браузера.
- **Запись звонка (п. 8.7)** — `GET /training/calls/{id}/recording` (`speech.py:CallRecordingHandler`): все реплики синтезом (оператор — роль `operator`) в один WAV/MP3, склейка — `domain/audio.py` (без ffmpeg). Ссылка — в `CallReview` и «запись» в журнале IP-телефона ДДС (`DdsSoftphone`).
- **Проверка без ключей и Docker:** `make dev-tts` (нейроголоса Piper по ролям, sherpa-onnx), `make dev-tts-say` (голос macOS) и `make dev-stt` (faster-whisper); модели скачиваются при первом запуске + переменные `TTS_*` / `STT_*` из таблицы режимов в `docs/ai/Голосовой_ввод.md`. Переключение OpenRouter ↔ локально ↔ Speaches — только переменными: адаптеры одни.
- **Без рук (V3)** — детектор фраз `frontend/src/shared/voice/vad.ts:VadDetector` (чистый модуль: `step(rms, now, partySpeaking)`; значения — из прототипа, гистерезис исправлен), микрофон — `useHandsFree.ts` (непрерывная запись с предзаписью: без неё Whisper теряет первое слово), фраза → WAV 16 кГц (`wav.ts`) → `POST /training/speech`. Правила состояния — по основам фраз, а не целым фразам: реплика приходит из распознавания с ошибками. В `CallPanel`: очередь голосовых реплик (`enqueue`, ответ модели не обрывается), перебивание (`onSpeechStart` → `stopVoice`), отсев эха `isLikelyEcho`; микрофон закрыт вне звонка и на время подсказок (`useActiveTour`). Сервер выбрасывает «титры» Whisper (`drop_phantoms`).
- **Удержание (ТЗ 6.1)** — статус `held`, `Call.hold/resume`, `POST /training/calls/{id}/hold|resume` (`HoldCallHandler`), реплики на удержании — 422 `call_held`; заявитель кладёт трубку после `telephony.hold_max_s` (настройка администратора). Кнопка — `CallPanel` («удержание» / «снять»).
- **Режим звонка** — `ReplicaIn.via` (`text` / `voice` / `hands_free`) → `training_call_messages.via` (миграция 0016), `CallView.mode`, `ReportCard.call_mode` → отчёт и CSV.
- **Преподавателю (V4):** разбор разговора — `shared/ui/CallReview.tsx` (кнопка «разговор» в отчёте занятия и «разговор с заявителем» в просмотре карточки); эмоция и напряжение — в пометке критерия в панели оценки; критерий `caller_care` «Работа с заявителем (информативно)» — `assessment/domain/scoring.py`, **вес 0** в `WEIGHTS_112` (не удаляйте ноль: критерий без веса получает 1,0 в `total`), факты — `IncidentAttempts._caller`; на плитке мониторинга — `ParticipantProgress.caller_emotion`, `caller_tension`.
- **Голосовой полигон** — страница `frontend/public/voice-lab/` (из прототипа `prototypes/emotional-voice-duplex`), сервер — `training/application/voice_lab.py:VoiceLab`, эндпоинты `/training/voice-lab/{stt,chat,tts}` (SSE в формате OpenAI), пункт меню — `CabinetShell.tsx:VOICE_LAB`. Подача голоса из скобок в начале текста уходит в `VoiceProfile.style`. В nginx CSP нужен `media-src blob:`.
- **Потоковый ответ (F1, ADR-0013)** — `POST /training/calls/{id}/replicas/stream` (SSE: `accepted`, `state`, `model`, `offline` — модель не ответила ни куском, `token`, `remark`, `replace`, `final` с `metrics`, `error`). Ход один для обоих эндпоинтов: обработчик, `PsyDirector.turn` и `Actors` принимают необязательный `EventSink` (`training/application/events.py`). Модель стримит через `TaskModel.stream` (адаптер без `LLMStreamPort` — одним куском). Обработчику потока нужна своя сессия БД — `StreamReplicaFactory` в bootstrap. Озвучка по фразам — `GET /calls/{id}/speak`, фронт — `CallPanel` (`feedPhrases`, предзагрузка звука), ремарки из потока вырезает `domain/stream_text.py:RemarkFilter`.
- Дальше — шаг модели (V5): [спецификация](specs/3.6-emotional-voice.md), [ADR-0011](docs/adr/0011-voice-emotional-caller.md).

## Психологический модификатор (п. 3.7, ADR-0012) — что уже есть
- **Каталог** — `data/dictionaries/psy_profiles.yaml` (15 профилей, у каждого `sources` — ссылки на `docs/research/psychology/`), проверяется при старте (`YamlPsyCatalog`). Новый код действия — в `training/domain/psy.py` (`GOOD_ACTS`/`BAD_ACTS`/`EVENTS`, `ACT_TITLES`), словарь — `psy_acts.py`, объяснение ошибки — `assessment/domain/psy_scoring.py:WHY`.
- **Состояние хранит движок, не модель:** `psy.py:step` (ECCS 1–5), `gates` (что заявитель может сказать), `voice_for` (контракт голоса). Ход — `training/application/psy.py:PsyDirector.turn`; снимок профиля — `training_calls.psy`, разметка — `training_call_messages.meta` (миграция 0018).
- **Выключен — ничего не меняется:** все ветки только при `call.psy`. Меняете звонки или оценку — прогоните `unit/test_psy.py` (бенчмарк мутаций) и прежние тесты.
- **Оценка** — блок `details.psy` (`assess_psy`, `timeline`), вес в итоге — `settings.psy.weight` (снимок в звонке). ИИ-судья блока — `psy_judge`, без модели «не проверено».
- **Голос** — эмоциональный голос п. 3.6: при профиле `CallerTone` выводится из состояния профиля (`psy.py:tone_from_psy`), так что синтез озвучивает то же состояние; модификатор отдаёт `ReplicaOut.voice`/`remarks`/`hung_up`, принимает `ReplicaIn.latency_ms`/`interrupted` (дуплекс-адаптер — `docs/ai/Психологический_модификатор.md` §11).
- **Фронт:** `SessionsPage.tsx:PsyForm`, `ScenariosPage.tsx:PsyPick`, `CallPanel` (ремарки, «пауза»), `shared/ui/PsyBlock.tsx` в `AssessmentPanel`.
- **Источники (F4)** — реестр `psy_profiles.yaml: sources`/`basis` (код = раздел `docs/research/psychology/01–03`), основания критериев и ошибок — `psy_scoring.py:CRITERIA_BASIS`/`ACT_SOURCES`; «Методика» — `GET /training/psy/methodology` (`psy_methodology.py`), `/teacher/methodology` и вкладка справочной базы; сводка ошибок группы — `stress_errors` → `SessionReport.psy_errors`. Новый код ошибки или критерий — с источником, иначе упадёт `unit/test_psy_sources.py`. Только официальные источники, без упоминаний вузов.

## Ветвящиеся сценарии (F5, ADR-0014) — что уже есть
- **Шаблоны:**
  - `data/dictionaries/branch_templates.yaml`: 4 шаблона, у каждого перехода и инструкции `source` из реестра `sources` (только официальные), контрольные ходы `checks`;
  - проверка при старте — `YamlBranchCatalog`, правила графа — `training/domain/branching.py:validate_graph`;
  - сценарий хранит снимок шаблона (`scenarios.branching`), звонок — факты и путь (`training_calls.branch`, миграция 0020).
- **Путь — чистая функция фактов:**
  - `resolve(tpl, facts, until, state)`, где факты — что и когда сказал оператор, что сообщил заявитель, когда сохранена карточка и с какими службами, статусы ДДС;
  - ход звонка ведёт `training/application/branching.py:BranchDirector`: шаг до ответа заявителя в `SendReplica`, тик `POST /training/calls/{id}/tick` раз в 5 с из `CallPanel`;
  - итог `view()` — тот же расчёт для оценки, разбора и доклада бригады.
- **Новая инструкция или развилка:**
  - фразы — в `instructions` шаблона (основы слов, у вредных — `harmful: true`, отрицание отсекается);
  - переход — в `edges` узла;
  - у неконечного узла обязателен переход только по времени (`note: didactic`, если это учебное упрощение);
  - после правки прогоните `unit/test_branching.py`: проверку графа, контрольные ходы и бенчмарк мутаций.
- **Заявитель:**
  - узел даёт «что происходит сейчас» в `applicant_actor/v4` (у профиля — блок к `v3`), факты поверх легенды и ворота ∪ ворота профиля;
  - `escalate` сдвигает `CallerTone` (причина `situation`) или уровень ECCS;
  - реплика-событие звучит один раз;
  - модель только переписывает реплики-события (`branch_texts`, проверка `check_event_text`).
- **Оценка** — блок `details.branch` (`assessment/domain/branch_scoring.py`):
  - итог 100 / 60 / 30 / 0 баллов;
  - вес — `settings.branch.weight`, по умолчанию 0 (информативно), снимок в звонке;
  - итог окончательный после конца звонка и сохранения карточки.
- **Выключено — ничего не меняется:** все ветки только при `call.branch`.
- **Фронт:**
  - `shared/ui/BranchOutcome.tsx` («Развитие ситуации» в `AssessmentPanel` и `CallReview`);
  - `pages/teacher/BranchGraphView.tsx` (вкладка «ветвление» в банке);
  - выбор шаблона в форме генерации, вес в форме занятия, «Развитие ситуаций» в отчёте занятия.

## Автооценка (п. 3.4) — что уже есть
- **Правила** — `modules/assessment/domain/scoring.py` (формулы и веса описаны в `specs/3.4-assessment.md`); ИИ-судья — `application/judge.py` (без модели критерии «не проверено»).
- **Попытка** (карточка, сценарий, статусы, звонки) — `aiskra/integration/assessment_sources.py`.
- **API:** `POST /api/v1/assessment/cards/{id}/evaluate {role: 112|dds, service_code?, weights?, norm_seconds?, threshold?}`, `GET /assessment/cards/{id}?role=`, `GET /assessment/insights`. Фронт — `shared/ui/AssessmentPanel.tsx`, инсайты — `RoleHomePage`. Запуск сам: 112 — после сохранения своей карточки, ДДС — как только у своей службы окончательный статус (`works_completed`, `works_refused`, `rejected`; поставлен сейчас — `fresh`, оценка заново), до него — без запуска.
- **Без модели** грамотность описания и комментариев ДДС проверяют правила `aiskra/shared/spelling.py:check_operator_text` (`assess.py:rules_grammar`); смысл и регламентность — «не проверено». Порядок звонков ДДС — `call_order_errors` (по `DdsAttempt.call_log`), время реакции по очереди — `stats.reaction_s` → отчёт (`max_time_s`, `over_norm`).
- **Инсайты по группе (ТЗ 3.13, 7.3)** — ИИ-задача `insights` (промпт `ai/prompts/insights/v1.md`), без модели — `assessment/domain/insights.py:rules_insights`.
- **Экспертная оценка окончательна:** `details.expert` переносится в каждую новую версию автооценки (`AssessCardHandler`), меняются только критерии и `auto_score`.

## Кабинет преподавателя: банк, занятия, отчёты (п. 4.1–4.3) — что уже есть
- **Каркас** — `shared/ui/TeacherShell.tsx` (ui-kit `AppShell`, `Sidebar`, `Topbar`); страницы — `pages/teacher/` (`/teacher/scenarios`, `/teacher/sessions`, `/teacher/sessions/:id`, `/teacher/sessions/:id/report`). Стили — `tch-*` в `packages/ui-kit/css/cabinet.css`.
- **Занятие** — домен `training/domain/session.py` (тип, источник карточек, участники с ролями, `DEFAULT_SETTINGS`); категории хранятся в `training_sessions.settings.groups`, участники — `assignments`. Карточка 112 привязывается к занятию через `session_id` в `POST /incidents/cards`.
- **Поток карточек ДДС** решает сервер: `POST /training/sessions/feed` (темп `feed_interval_s`, предел `max_waiting`); системная карточка — `integration/session_sources.py::IncidentSystemCards` (`origin = system`, автор — преподаватель).
- **Мониторинг** — `GET /training/sessions/{id}/monitor` (`SessionProgress`), **отчёт** — `GET /assessment/sessions/{id}/report` и `report.csv` (факты — `SessionFactsReader`), **правка** — `POST /assessment/{id}/override` (только оценки своего занятия, порог — из настроек занятия; порт `CardLessons`), **прогресс** — `GET /assessment/my/progress`.
- **Один ответ из прогона (ТЗ 3.4)** — `PUT /training/scenarios/{id}/answers/{topic}` (`EditAnswerHandler`): вручную или моделью по комментарию; ответы — `legend.answers`, их говорит заявитель в звонке; факты легенды проверяет `training/domain/actors.py:answer_fact_errors`.
- **Частичное утверждение эталона (п. 3.3)** — `training/domain/review.py` (разделы `SECTIONS`, решение с отпечатком содержимого — правка раздела сбрасывает только его решение), `POST /training/scenarios/{id}/review`, фронт `pages/teacher/ReferenceReview.tsx`. Новый раздел эталона — ключ в `SECTIONS` и ветка в `section_content`.
- **Обучающийся** — `GET /training/sessions/my` (для всех ролей, `null` вне занятия); баннер — `shared/ui/SessionBanner.tsx`.
- **Аналитика (п. 4.5)** — `assessment/application/queries/analytics.py` (`TeacherAttempts` собирает попытки по занятиям преподавателя из `SessionFactsReader` и оценок), чистые функции — `assessment/domain/analytics.py`. Эндпоинты `/assessment/analytics/{norms,students/{id},suggest}` и `/assessment/sessions/{id}/debrief`, экраны — `pages/teacher/analytics/`. Нормативы — ПП РФ № 1931 (карточка 75 с, ДДС 30 с), основания — `docs/research/`.
- **Достоверность (п. 3.5)** — методика `assessment/domain/validation.py` (мутации, κ, согласие с экспертом), `GET /assessment/analytics/validation`, экран `/teacher/validation`, отчёт — `tools/validate_ai.py` → `docs/validation/`. Меняете правила автооценки — прогоните бенчмарк: `unit/test_validation.py` должен остаться зелёным.
- **Допуск (п. 4.6)** — шкала `assessment/domain/readiness.py`, запрос `ReadinessHandler`, `GET /assessment/analytics/readiness`; экраны `/teacher/readiness` и `/teacher/readiness/protocol` (печать).

## Отзыв преподавателя по занятию (п. 4.7) — что уже есть
- **Черновик** — `POST /assessment/sessions/{sid}/students/{uid}/feedback/draft` (`DraftFeedbackHandler`): ИИ-задача `feedback_draft`, промпт `ai/prompts/feedback_draft/v1.md`. Без модели или при её ошибке черновик собирают правила `assessment/domain/feedback.py` (`summarize` → `rules_draft` → `compose`). В модель — `model_facts()`: без ФИО и без названия занятия, в нём бывает ФИО. Черновик ничего не сохраняет.
- **Сохранение** — `PUT …/feedback` (`SaveFeedback`, право `lessons.conduct` и только своё занятие): таблица `teacher_feedback` (миграция 0017), одна запись на «занятие + обучающийся», событие аудита `assessment.feedback_saved`. В `details` — снимок `focus`/`criteria`: следующий черновик сравнивает с ним «было → стало». Там же `draft.similarity` — насколько преподаватель поправил черновик.
- **Где видно:** отчёт — `StudentReport.feedback`, блок `pages/teacher/StudentFeedback.tsx` в раскрытой строке, колонка в CSV; обучающийся — `GET /assessment/my/feedback` (история в `StudentHomePage`) и `…/mine` (`MySessionPage`).

## Кабинеты обучающегося и администратора (п. 5.1, 5.2) — что уже есть
- **Каркас** всех кабинетов — `shared/ui/CabinetShell.tsx` (разделы ролей в `NAV`); `TeacherShell` — обёртка над ним.
- **Обучающийся:** `/student` (занятия, вход в эмулятор `armFor()`, история), `/student/sessions/:id` (`GET /assessment/sessions/{id}/mine`), `/student/progress`, `/student/reference`. Рекомендации — `assessment/domain/recommendations.py`. Комментарий возврата — `CardView.rework` (из аудита).
- **Администратор:** `/admin` (состояние `GET /system/status`, импорт), `/admin/users`, `/admin/groups` (`/groups`, читать может и преподаватель), `/admin/settings` (`system_settings`, копии `platform/backup.py`), `/admin/logs` (`platform/logbuffer.py`).
- **Роль оператора 112** (рекомендации экспертов: приоритет — ДДС) — `services.role_112`, по умолчанию 0 — скрыта; фронт узнаёт из `Me.features` (`auth.ts:role112`), экраны 112 — `RequireAuth feature="role_112"`. Тесты e2e и смоук CI включают её администратором.
- **Применяются сразу** (порт `RuntimeSettings` → `platform/logbuffer.ProcessRuntime`, при старте — `bootstrap.apply_runtime_settings`): раздел `logging.level`. Раздел `telephony.hold_max_s` читает training через `TelephonySettings` (`integration/system_sources.py`).
- **Настройки по умолчанию** для занятий — порт `SessionDefaults` (адаптер `integration/system_sources.py`); новый раздел настроек — ключ в `LIMITS` (`system/application/commands/settings.py`).
- **Резервная копия** выгружает все таблицы из `models_registry`, кроме `dict_*` и `auth_sessions`: новая таблица попадает в копию сама.
- `require(Permission.A, Permission.B)` — «любое из прав».

## Обучение интерфейсу (п. 5.3, 5.4) — что уже есть
- Прогресс — `users.onboarding` (JSON `{dismissed, seen[]}`, миграция 0012), домен `identity/domain/onboarding.py`, API `GET/POST /auth/onboarding` (`seen` с `tours: [...]` одной записью · `dismiss` · `reset`). Сами подсказки показываются своей **аудитории** — `audience` по правам: `training.participate` → `student`, `lessons.conduct` → `teacher`, администратору — никому.
- **Экраны преподавателя (5.4)** — `TEACHER_TOURS`, id с префиксом `teacher-` (по нему `tourAudience`), обзор — `TEACHER_WELCOME`; кнопка «подсказки» в шапке кабинета — `TourCabinetButton`. Цель на карточке — `<Card tour="…">` (ui-kit). Какие экраны получают подсказки, а какие нет, и почему — `specs/5.4-teacher-onboarding.md`, таблица 7.1: новый экран преподавателя — сначала туда.
- Фронт: тексты — `shared/onboarding/tours.ts`, подсветка — `Tour.tsx`, логика показа — `OnboardingProvider.tsx`. **Новый экран обучающегося:** описание в `TOURS`, на странице `useScreenTour('<id>', <данные загружены>)`, цели — `data-tour="…"` или существующие `id`. Меняете разметку экрана — проверьте, что селекторы в `tours.ts` ещё находят элементы (шаг без цели молча пропускается).
- Пауза учебных таймеров на первые подсказки: правило — `incidents/domain/timer_pause.py` (всего до 10 мин, каждая пауза — в аудит). Карточка 112 — `IncidentCard.pause_timer/resume_timer`, `POST /incidents/cards/{id}/timer`; `processing_ms` уже без паузы. ДДС — `card_services.paused_ms`, `POST /incidents/dds/{service}/timer` (карточка или вся очередь). **Новый расчёт времени** «от открытия» или «от поступления в службу» делайте за вычетом `paused_ms`. Фронт — `useTourPause(tourId, enabled, {set, onEnd, onSynced})`.

## Учебные материалы (п. 4.4) — что уже есть
- Домен `training/domain/material.py` (тип по сигнатуре, выдержки, `best_passages`); файлы — `LocalFileStorage` (`materials_dir`), текст — таблица `materials`; извлечение — `DocumentTextExtractor`.
- API `/training/materials` (загрузка multipart, список, текст, файл, правка, удаление); фронт — `pages/teacher/MaterialsPage.tsx`, `shared/ui/MaterialViewer.tsx`, вкладка в `student/ReferencePage.tsx`.
- Выдержки в генерацию: порт `MaterialContext` → `ScenarioGenerator(..., materials=)`; только для материалов с `use_in_prompts`.

## Производительность и устойчивость (п. 6.1) — что уже есть
- **Нагрузка:** `backend/tools/loadtest.py` (учётки — `demo-seed --load-users 100`, объём — `tools/bulk_seed.py`); результаты — `docs/performance/`.
- **Журнал ДДС** считает и сортирует по `card_services.card_saved_at`/`card_number` (копия при сохранении карточки): новый путь записи строк служб обязан их заполнять.
- **Подсчёт `total`** — отдельным лёгким запросом, без вычисляемых столбцов страницы.
- **Фронт:** запись — с `WRITE_RETRY` (`shared/api/resilience.ts`); ошибка «уже выполнено» при повторе = успех. Приложение считается всегда активным (`focusManager` в `main.tsx`).

## Адаптивность и локализация (п. 6.3) — что уже есть
- **Кабинеты** — телефон от 360 px: нижняя панель со всеми разделами (`CabinetShell`), таблицы листаются внутри `.cab-card__body`. Новая страница кабинета — проверьте на 375 px, что у страницы нет горизонтальной прокрутки.
- **Эмулятор АРМ** — от 1000 px; маршрут `/arm/*` оборачивайте в `ArmScreenGuard` (как в `app/router.tsx`).
- **Числа и размеры** — `shared/format.ts` (`num`, `bytes`), не `toFixed` и не «как есть». Ошибки проверки 422 переводит `platform/validation_ru.py`; новый тип ошибки pydantic — строка в `MESSAGES`.

## E2E (F6.5) — сквозные сценарии в браузере
- **Запуск:** `make e2e` (сборка фронтенда, браузер Playwright, прогон ≈ 1,5–2 мин); Firefox — `make e2e E2E_BROWSER=firefox`. `make be-test` и голый `pytest` e2e не собирают: `testpaths` в `backend/pyproject.toml` — только `unit` и `integration`, у тестов маркер `e2e`.
- **Стенд поднимает фикстура `stand`** (`backend/tests/e2e/conftest.py`, один раз на сессию): временная SQLite — миграции, `import-dictionaries`, `import-addresses`, `ensure-admin`, `demo-seed` (пароли генерирует тест, сценарии — офлайн); модель-заглушка `tests/e2e/mock_llm.py` (только stdlib: `/chat/completions` с потоком и без, JSON по схеме из промпта, `/audio/speech` → WAV, `/audio/transcriptions` → `STT_TEXT`); backend — uvicorn с `config/ai.openrouter.yaml`, `AISKRA_APP_ENV=demo` и `DEMO_LLM_URL`/`TTS_*`/`STT_*` на заглушку; фронтенд — `vite preview` собранного `dist` с прокси `/api`. Порты свободные, переменные разработчика (`AISKRA_*`, `DEMO_*`, `TTS_*`, `STT_*`) в стенд не попадают, внешней сети нет (`allow_external: false`).
- **Тест** берёт `ui: Session` → `ui.new_page("op1")` (контекст с cookie входа; `voice=True` — включённая озвучка). Каждый тест проверяет консоль: ошибка JavaScript или ответ API 5xx — падение; ожидаемый отказ — `ui.errors.allow(шаблон)`. При падении — снимок экрана, консоль и журналы стенда в `backend/tests/e2e/artifacts/<тест>/` (в `.gitignore`).
- **Данные:** подготовка, которая не проверяется в тесте, — через API (`stand.client(login)`, `helpers.py`: занятие, карточка с вызовом); проверяемое — через интерфейс. Учётки для тестов отказов и полигона — `load001…003` (`demo-seed --load-users`), чтобы не мешать занятиям `op1`/`op2`. Отказы: `stand.mock.stop()/start()`, `stand.mock.fail_tts`, `stand.backend.restart()`.
- **Синтетический микрофон** Chromium — WAV из `mock_llm.tone_wav` (тишина → «фраза» → тишина): VAD полигона и кнопка «говорить» получают фразу, распознавание отдаёт `STT_TEXT`.
- Новый экран или сценарий — тест в `tests/e2e/` и строка в трассировке `specs/F6-e2e.md`. Меняете подписи кнопок или `aria-label` — прогоните `make e2e`: селекторы — по ним.

## Пояснительная записка (п. 7.2) — что уже есть
- `docs/delivery/Пояснительная_записка.md` — исходник; модель данных, API, матрица ТЗ и библиотеки подставляются сборщиком `docs/delivery/build.py` из кода. Закрыли пункт плана — обновите статус требования в `MATRIX` и пересоберите: `cd backend && uv run --with python-docx --with pypandoc_binary --with pypdfium2 python ../docs/delivery/build.py` (нужен LibreOffice). Готовые файлы — `docs/delivery/out/`, коммитятся.

## Рецепты
**Новая команда** (пример: `SaveCard` в `incidents`):
1. `modules/incidents/application/commands/save_card.py` — `@dataclass(frozen=True, kw_only=True) class SaveCard(Command)` и `class SaveCardHandler` с зависимостями-портами в `__init__` и `async __call__(cmd) -> Result`.
2. Порты, если нужны новые: `application/ports/*.py` (`Protocol`). Реализации: `infrastructure/*.py`.
3. `api/deps.py`: `provide_save_card_handler = provider_stub("incidents.SaveCardHandler")`. `api/router.py`: эндпоинт с `Depends(deps.provide_save_card_handler)`. `api/schemas.py`: pydantic-схемы.
4. `bootstrap.wire()`: связать заглушку с фабрикой; для запроса с БД — фабрика с `Depends(get_session)`.
5. Права и аудит — см. раздел «Безопасность» выше.
6. Тесты: unit — обработчик с фейками портов; integration — эндпоинт через `TestClient` под нужной ролью, плюс 403 для чужой роли.

**Новый запрос**: то же, но `Query` и без UoW. Чтение делайте простым SQL или ORM-выборкой прямо в DTO, агрегаты не собирайте.

**Новая ИИ-задача:** значение в `ai/tasks.py:AITask` → запись в `config/ai.yaml` и `config/ai.example.yaml` → сервис в application модуля использует `router.for_task(...)`. Промпт хранится версионированно (`prompt_version` в конфиге задачи).

**Новый провайдер модели:** класс в `ai/adapters/`, реализующий `LLMPort` → ветка в `ai/adapters/factory.build_llm` → значение `kind` в `ai/config.ProviderConfig`. Остальной код не меняется.

## Definition of Done для задачи
- Пункт плана закрыт по спецификации `specs/<пункт>-<кратко>.md`: создайте её по [шаблону](specs/_template.md) до начала работы. Трассировка (код, тесты, статусы) обновлена в том же коммите.
- Тесты на новую логику, все проверки зелёные.
- Нет секретов и реальных ПДн: только синтетические данные.
- Интерфейс карточки и реестра — **визуально как АРМ заказчика** (ответы заказчика #679/#680). Используйте `packages/ui-kit`, новые цвета не изобретайте.
- Обновлены документы, если меняется поведение: spec, ADR (для решений), README.

## Нельзя
- Хардкодить внешние адреса моделей, обходить `ModelRouter`, класть ключи и пароли в git.
- Подключать роутер в `main.py` без `dependencies=signed_in` (кроме `/auth`). Проверять роль строкой вместо `Permission`.
- Писать в журнал аудита мимо `AuditRecorder`, изменять или удалять записи аудита.
- Импортировать `fastapi` / `sqlalchemy` / адаптеры в `domain` или `application`.
- Менять схему БД без миграции, редактировать применённые миграции.
- Коммитить в `main` напрямую. Работаем в ветках `feat/<пункт-плана>-<кратко>`, коммиты — [Conventional Commits](docs/rules/git.md) на русском.
