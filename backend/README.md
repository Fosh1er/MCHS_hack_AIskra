# backend — АИскра

FastAPI + SQLAlchemy 2 (async) + PostgreSQL. Модульный монолит, чистая архитектура, CQRS-lite, порты и адаптеры для ИИ.
Правила и рецепты — в корневом [AGENTS.md](../AGENTS.md), решения — в [docs/adr](../docs/adr).

```bash
uv sync                      # зависимости (Python 3.12)
uv run pytest                # тесты
uv run ruff check . && uv run mypy && uv run lint-imports   # стиль, типы, архитектурные контракты
uv run alembic upgrade head  # миграции (нужен PostgreSQL, см. AISKRA_DATABASE_URL)
uv run uvicorn aiskra.main:app --reload   # http://localhost:8000/docs
```
