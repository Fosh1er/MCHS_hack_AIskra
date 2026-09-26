# 0007. Стек

- **Статус:** Принято · **Дата:** 2026-09-26 · **Пункты плана:** 0.1

| Слой | Выбор | Почему |
|---|---|---|
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 async, Alembic | Одна экосистема с ИИ, async для WebSocket, OpenAPI из коробки |
| БД | PostgreSQL 16 | ТЗ: PostgreSQL ≥ 12; JSONB для карточек и эталонов |
| Качество | uv, ruff, mypy --strict, import-linter, pytest | Быстро, строгие типы, архитектурные контракты в CI |
| Frontend | React 18, Vite, TypeScript, TanStack Query, react-router | Совпадает с UI-китом; CQRS на фронте: useQuery / useMutation |
| UI | `packages/ui-kit` (npm workspace) | Копия интерфейса АРМ по скриншотам заказчика |
| Запуск | docker compose (db, backend, frontend; профиль `local-llm` — Ollama) | Офлайн-развёртывание одной командой |
