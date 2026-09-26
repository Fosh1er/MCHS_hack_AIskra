# АИскра — ИИ-тренажёр оператора 112 и диспетчера ДДС

Хакатон «Лидеры цифровой трансформации 2026», задача №9 (Департамент ГОЧСиПБ Москвы, ГБУ «Система 112»).
Учебное ПО: имитация АРМ-112 и АРМ-ДДС, генерация сценариев и автооценка с помощью ИИ, работа в изолированном контуре.

## Майлстоуны

Дедлайн сдачи — **29.09.2026 23:59 МСК**, дальше стоп-код. Статусы как в [specs](specs/README.md): ✅ сделано · 🟡 частично · ⏳ не начато. Пункты — из [плана работ](docs/brief/02_План_работ.md). Таблица обновляется в том же PR, что закрывает пункт.

| # | Майлстоун | Срок | Статус | Пункты плана | Что осталось |
|---|---|---|---|---|---|
| M0 | Анализ требований и план | 26.09 | ✅ | — | [docs/brief](docs/brief/00_README.md) |
| M1 | Фундамент | 26.09 | ✅ | [0.1](specs/0.1-architecture.md) ✅ · [0.2](specs/0.2-data-model.md) ✅ · [0.3](specs/0.3-auth-rbac-audit.md) ✅ | проверка `docker compose` на машине с Docker |
| M2 | Эмулятор АРМ-112 | 27.09 | 🟡 | [1.1](specs/1.1-card-112.md) ✅ · [1.2](specs/1.2-address-map.md) ✅ · [1.3](specs/1.3-journal.md) ✅ · [1.4](specs/1.4-incoming-call.md) 🟡 · [1.5](specs/1.5-auto-services.md) 🟡 · 1.6 ⏳ (P2) | голос оператора (распознавание), входящее СМС; подчинённость объектов в автоподборе |
| M3 | Эмулятор АРМ ДДС | 27–28.09 | ✅ | [2.1](specs/2.1-dds-journal.md) ✅ · [2.2](specs/2.2-dds-card.md) ✅ · [2.3](specs/2.3-dds-phone.md) ✅ · 2.4 🟡 (P1) | — (источник карточек и темп — в 4.2) |
| M4 | ИИ-модуль | 27–28.09 | ✅ | 3.1 ✅ · [3.2](specs/3.2-scenario-generation.md) ✅ · [3.3](specs/3.3-dialog-agents.md) ✅ · [3.4](specs/3.4-assessment.md) ✅ · 3.5 ⏳ (P1) | валидация качества ИИ (сравнение с экспертной оценкой) |
| M5 | Преподаватель, обучающийся, админ | 28.09 | ✅ | [4.1](specs/4.1-scenario-bank.md) ✅ · [4.2](specs/4.2-sessions.md) ✅ · [4.3](specs/4.3-reports.md) ✅ · [4.4](specs/4.4-materials.md) ✅ · [5.1](specs/5.1-student-cabinet.md) ✅ · [5.2](specs/5.2-admin-panel.md) ✅ | автокопии по расписанию; RAG на эмбеддингах (P2) |
| M6 | Сквозной сценарий | 28.09 вечер | ✅ | [M6](specs/M6-e2e.md) ✅ · [сценарий показа](docs/demo/M6_сквозной_сценарий.md) · `make demo-seed` | прогон в `docker compose` на сервере (M7) |
| M7 | Сдача | 29.09 до 22:00 | ⏳ | 6.1–6.3 · 7.1–7.4 | сопроводительная документация, презентация (слайды 7–11 по шаблону), стенд, скринкаст, заморозка |

## Быстрый старт
```bash
cp .env.example .env
docker compose up --build        # frontend :8080 · backend :8000/docs · PostgreSQL :5432
```
Справочники (один раз после первого запуска): `docker compose exec backend python -m aiskra.cli import-dictionaries` и `docker compose exec backend python -m aiskra.cli import-addresses` (адреса и границы районов, п. 1.2), `docker compose exec backend python -m aiskra.cli generate-scenarios --count 30` (банк учебных вызовов, п. 3.2). Учебные материалы (инструкция, памятки, п. 4.4) — страница «Учебные материалы» у преподавателя или `python -m aiskra.cli import-materials ФАЙЛ --kind instruction --as admin --prompts`.
Стенд для показа одной командой: `AISKRA_DEMO_PASSWORD=… make demo-seed` (учётки teacher, op1, op2, dds1, dds2 и группа; [сценарий показа](docs/demo/M6_сквозной_сценарий.md)).
Первый вход: задайте в `.env` пароль `AISKRA_BOOTSTRAP_ADMIN_PASSWORD` (не короче 8 символов) — при старте создаётся администратор `admin`. Панель администратора — `/admin`: пользователи, группы, настройки, резервные копии (том `backups`), импорт справочников, логи. Пользователей можно завести и командой `uv run python -m aiskra.cli create-user`.
По умолчанию ИИ работает офлайн (fake-модель). Подключение локальной модели или демо-API — в `config/ai.example.yaml` и [ADR-0003](docs/adr/0003-ports-adapters-ai.md).

## Разработка
```bash
make be-install && make be-check   # backend: uv, ruff, mypy --strict, import-linter, pytest
make fe-install && make fe-dev     # frontend: http://localhost:5173 (прокси на :8000)
```

## Документация
- [AGENTS.md](AGENTS.md) — правила и рецепты для разработчиков и кодинговых агентов
- [docs/brief](docs/brief/00_README.md) — анализ задачи: требования, план работ, карточка 112, интерфейс АРМ, классификатор, ответы заказчика
- [data/source/screenshots](data/source/screenshots) — скриншоты АРМ заказчика, на которые ссылается документация
- [specs](specs/README.md) — спецификации пунктов плана: требования → реализация → тесты (трассировка)
- [docs/adr](docs/adr/README.md) — архитектурные решения
- [docs/architecture/overview.md](docs/architecture/overview.md) — обзор архитектуры
- [packages/ui-kit](packages/ui-kit/README.md) — библиотека стилей АРМ

## Стек
FastAPI · SQLAlchemy 2 · PostgreSQL 16 · React 18 · Vite · TypeScript · TanStack Query · docker compose
