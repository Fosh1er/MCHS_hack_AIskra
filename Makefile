# Частые команды. Бэкенд: uv (Python 3.12), фронтенд: npm workspaces (Node 22).
.PHONY: up down logs be-install be-test be-lint be-check fe-install fe-dev fe-build check import-classifier demo-seed demo-seed-docker

up:            ; docker compose up --build -d
down:          ; docker compose down
logs:          ; docker compose logs -f backend
be-install:    ; cd backend && uv sync
be-test:       ; cd backend && uv run pytest -q
be-lint:       ; cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports
be-check: be-lint be-test
# M6: стенд одной командой (справочники, адреса, сценарии, учётки ролей, группа). Пароль — AISKRA_DEMO_PASSWORD.
demo-seed:     ; cd backend && uv run python -m aiskra.cli demo-seed $(if $(MATERIALS),--materials $(MATERIALS),)
demo-seed-docker: ; docker compose exec -e AISKRA_DEMO_PASSWORD backend python -m aiskra.cli demo-seed
fe-install:    ; npm install
fe-dev:        ; npm run dev
fe-build:      ; npm run typecheck && npm run build
check: be-check fe-build
