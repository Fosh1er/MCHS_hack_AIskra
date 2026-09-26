# Частые команды. Бэкенд: uv (Python 3.12), фронтенд: npm workspaces (Node 22).
.PHONY: up down logs be-install be-test be-lint be-check fe-install fe-dev fe-build check import-classifier

up:            ; docker compose up --build -d
down:          ; docker compose down
logs:          ; docker compose logs -f backend
be-install:    ; cd backend && uv sync
be-test:       ; cd backend && uv run pytest -q
be-lint:       ; cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports
be-check: be-lint be-test
fe-install:    ; npm install
fe-dev:        ; npm run dev
fe-build:      ; npm run typecheck && npm run build
check: be-check fe-build
