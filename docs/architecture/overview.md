# Архитектура — обзор

```
Браузер (React SPA, ui-kit)                     опрос /api/v1 раз в 5 с (журналы, мониторинг), без WebSocket
   │  HTTPS
   ▼
nginx (TLS, статика SPA, gzip) ──► backend (FastAPI, один процесс — ADR-0005)
            ├─ modules/<m>/api            входящие адаптеры (HTTP)
            ├─ modules/<m>/application    команды · запросы · порты  (CQRS-lite, ADR-0002)
            ├─ modules/<m>/domain         чистая бизнес-логика
            ├─ modules/<m>/infrastructure ORM, репозитории, импорт
            ├─ integration/               адаптеры портов одного модуля поверх данных другого
            ├─ ai/  ModelRouter → CachingLLM → OpenAICompatibleLLM | FakeLLM   (ADR-0003, 0006)
            ├─ platform/                  БД, настройки, заголовки безопасности, копии, логи, состояние
            └─ bootstrap.py               composition root (ADR-0004)
   │
   ▼
PostgreSQL 16            модель: Ollama/vLLM/llama.cpp (профиль local-llm) или внешний API на демо
```

## Модули
| Модуль | Отвечает за |
|---|---|
| `identity` | вход, сессии, пользователи, группы обучающихся, прогресс обучения интерфейсу |
| `dictionaries` | классификатор, службы и матрица маршрутизации, территория, адреса, импорт |
| `incidents` | карточка 112, журнал, статусы, АРМ ДДС (службы карточки, статусы службы) |
| `training` | сценарии, ИИ-собеседники и звонки, занятия, учебные материалы |
| `assessment` | автооценка по эталону, экспертная правка, отчёты, прогресс, рекомендации |
| `audit` | журнал аудита: запись, поиск, ретеншн |
| `system` | настройки, резервные копии, логи, состояние сервисов, диагностика ИИ |

Модули не импортируют друг друга (проверяет `import-linter`). Когда модулю нужны данные другого — порт в своём `application/ports`, адаптер в `integration/`, связывание — в `bootstrap.py`. Пример: автооценка (`assessment`) читает карточку и сценарий через `integration/assessment_sources.py`.

## Поток запроса к API (ADR-0010)
cookie `aiskra_session` → `provide_principal` (запрос `ResolveSession`: сессия + пользователь из БД) → `Principal` →
`require(Permission.X)` (иначе 403 и «Отказ в доступе» в аудит) → эндпоинт. Без действующей сессии — 401; это проверяет тест по всем маршрутам (`test_security.py`).

## Поток команды
HTTP → pydantic-схема → `Command(actor, meta, …)` → `Handler(ports)` → домен → репозиторий → `AuditRecorder.record()` →
`UnitOfWork.commit()` → DTO → схема ответа.

## Поток запроса
HTTP → `Query` → обработчик чтения (SQL → DTO) → схема ответа.

## Вызов ИИ
Сервис application → `router.for_task(task)` → `TaskModel` подставляет параметры и кеш из конфига → `CachingLLM` (ключ, single-flight) → адаптер провайдера. Без модели (`fake`) — детерминированные ответы по легенде; генерация сценариев получает выдержки из учебных материалов (п. 4.4).

## Где что настраивается
| Что | Где |
|---|---|
| БД, окружение, CORS, каталоги копий и материалов | переменные `AISKRA_*` (`.env.example`) |
| Сессии, блокировка подбора пароля, начальный администратор | `AISKRA_SESSION_*`, `AISKRA_LOGIN_*`, `AISKRA_BOOTSTRAP_ADMIN_*` |
| TLS, имя сервера в сертификате | том `tls`, переменная `TLS_SAN` (`infra/nginx/`) |
| Роли и права | `backend/src/aiskra/shared/security.py` (`ROLE_PERMISSIONS`) |
| Модели на задачи, кеш, изолированный контур | `config/ai.yaml` (пример — `config/ai.example.yaml`) |
| Тайминг занятий по умолчанию, хранение копий, срок хранения аудита | панель администратора → «Настройки и копии» (таблица `system_settings`) |
| Справочники | `data/` + импорт в панели администратора или `python -m aiskra.cli import-dictionaries` |
