# АИскра — ИИ-тренажёр оператора 112 и диспетчера ДДС

Хакатон «Лидеры цифровой трансформации 2026», задача №9 (Департамент ГОЧСиПБ Москвы, ГБУ «Система 112»).
Учебное ПО: имитация АРМ-112 и АРМ-ДДС, генерация сценариев и автооценка с помощью ИИ, работа в изолированном контуре.

## Быстрый старт
```bash
cp .env.example .env
docker compose up --build        # frontend :8080 · backend :8000/docs · PostgreSQL :5432
```
Первый вход: задайте в `.env` пароль `AISKRA_BOOTSTRAP_ADMIN_PASSWORD` (не короче 8 символов) — при старте создаётся администратор `admin`. Преподавателей и обучающихся создаёт администратор (`POST /api/v1/users`) или команда `uv run python -m aiskra.cli create-user`.
По умолчанию ИИ работает офлайн (fake-модель). Подключение локальной модели или демо-API — в `config/ai.example.yaml` и [ADR-0003](docs/adr/0003-ports-adapters-ai.md).

## Разработка
```bash
make be-install && make be-check   # backend: uv, ruff, mypy --strict, import-linter, pytest
make fe-install && make fe-dev     # frontend: http://localhost:5173 (прокси на :8000)
```

## Документация
- [AGENTS.md](AGENTS.md) — правила и рецепты для разработчиков и кодинговых агентов
- [docs/brief](docs/brief) — требования и план работ
- [specs](specs/README.md) — спецификации пунктов плана: требования → реализация → тесты (трассировка)
- [docs/adr](docs/adr/README.md) — архитектурные решения
- [docs/architecture/overview.md](docs/architecture/overview.md) — обзор архитектуры
- [packages/ui-kit](packages/ui-kit/README.md) — библиотека стилей АРМ

## Стек
FastAPI · SQLAlchemy 2 · PostgreSQL 16 · React 18 · Vite · TypeScript · TanStack Query · docker compose
