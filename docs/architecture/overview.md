# Архитектура — обзор

```
Браузер (React SPA, ui-kit)
   │  REST /api/v1 · WebSocket /ws · /health
   ▼
nginx ──► backend (FastAPI, один процесс — ADR-0005)
            ├─ modules/<m>/api            входящие адаптеры (HTTP)
            ├─ modules/<m>/application    команды · запросы · порты  (CQRS-lite, ADR-0002)
            ├─ modules/<m>/domain         чистая бизнес-логика
            ├─ modules/<m>/infrastructure ORM, репозитории, импорт
            ├─ ai/  ModelRouter → CachingLLM → OpenAICompatibleLLM | FakeLLM   (ADR-0003, 0006)
            └─ bootstrap.py  composition root (ADR-0004)
   │
   ▼
PostgreSQL 16            модель: Ollama/vLLM/llama.cpp (профиль local-llm) или внешний API на демо
```

## Поток запроса к API (ADR-0010)
cookie `aiskra_session` → `provide_principal` (запрос `ResolveSession`: сессия + пользователь из БД) → `Principal` →
`require(Permission.X)` (иначе 403 и «Отказ в доступе» в аудит) → эндпоинт. Без действующей сессии — 401.

## Поток команды
HTTP → pydantic-схема → `Command(actor, meta, …)` → `Handler(ports)` → домен → репозиторий → `AuditRecorder.record()` →
`UnitOfWork.commit()` → DTO → схема ответа.

## Поток запроса
HTTP → `Query` → обработчик чтения (SQL → DTO) → схема ответа.

## Вызов ИИ
Сервис application → `router.for_task(task)` → `TaskModel` подставляет параметры и кеш из конфига → `CachingLLM` (ключ, single-flight) → адаптер провайдера.

## Где что настраивается
| Что | Где |
|---|---|
| БД, окружение, CORS | переменные `AISKRA_*` (`.env.example`) |
| Сессии, блокировка подбора пароля, начальный администратор | `AISKRA_SESSION_*`, `AISKRA_LOGIN_*`, `AISKRA_BOOTSTRAP_ADMIN_*` |
| Роли и права | `backend/src/aiskra/shared/security.py` (`ROLE_PERMISSIONS`) |
| Модели на задачи, кеш, изолированный контур | `config/ai.yaml` (пример — `config/ai.example.yaml`) |
| Справочники | `data/` + `python -m aiskra.cli import-dictionaries` |
