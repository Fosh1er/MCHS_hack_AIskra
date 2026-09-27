# Backend АИскра: Python 3.12 + uv. Сборка: docker compose build backend
FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /app/backend

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
COPY tools ./tools
RUN uv sync --frozen --no-dev

ENV PATH="/app/backend/.venv/bin:$PATH" \
    AISKRA_AI_CONFIG_PATH=/app/config/ai.yaml
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"
# Миграции → начальный администратор (если задан AISKRA_BOOTSTRAP_ADMIN_PASSWORD) → API.
# --proxy-headers: реальный IP клиента из X-Forwarded-For от nginx попадает в аудит.
CMD ["sh", "-c", "alembic upgrade head && python -m aiskra.cli ensure-admin && uvicorn aiskra.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
