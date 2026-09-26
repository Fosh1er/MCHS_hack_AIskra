# Перечень библиотек и лицензий

Для требования ТЗ «перечень библиотек» (п. 7.1, 01 разд. 11.1). Версии — из `backend/uv.lock` и `package-lock.json` на 27.09.2026. Обновить: `uv run --with pip-licenses pip-licenses` в `backend/`, `npm ls` в корне.

Все зависимости — под свободными лицензиями (MIT, BSD, Apache-2.0, ISC, PSF; шрифт Roboto — OFL). Две транзитивные — certifi и pathspec — под MPL 2.0: это слабый копилефт на уровне файлов самой библиотеки, используем их без изменений, на лицензию проекта не влияет. Модели ИИ в репозиторий не входят: локальная модель скачивается отдельно (Ollama; лицензия модели — у её автора), внешний API подключается по договору заказчика.

## Данные

| Данные | Источник | Лицензия | Где |
|---|---|---|---|
| Адресный справочник Москвы, границы районов | © участники OpenStreetMap | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/): при показе нужна ссылка «© OpenStreetMap contributors» | `data/dictionaries/addresses.csv.gz`, `districts_geo.json`; генератор — `data/tools/build_addresses.py` |
| Классификатор происшествий v046, скриншоты АРМ | материалы заказчика (ГБУ «Система 112») к задаче хакатона | предоставлены для хакатона; публичное распространение — по согласованию с заказчиком | `data/source/` |
| Учебные данные (заявители, телефоны, легенды) | генерируются системой | синтетические | — |

## Бэкенд (Python) — прямые зависимости

| Библиотека | Версия | Лицензия | Назначение |
|---|---|---|---|
| alembic | 1.20.0 | MIT | миграции БД |
| asyncpg | 0.31.0 | Apache-2.0 | драйвер PostgreSQL |
| fastapi | 0.141.1 | MIT | веб-API |
| httpx | 0.28.1 | BSD | HTTP-клиент (ИИ-провайдеры) |
| openpyxl | 3.1.5 | MIT | чтение классификатора XLSX |
| pydantic | 2.13.5 | MIT | схемы и проверка данных |
| pydantic-settings | 2.15.0 | MIT | настройки из окружения |
| pypdf | 6.19.0 | BSD-3-Clause | текст из PDF (учебные материалы) |
| python-multipart | 0.0.32 | Apache-2.0 | загрузка файлов |
| PyYAML | 6.0.3 | MIT | конфигурация ИИ |
| SQLAlchemy | 2.1.1 | MIT | ORM, доступ к БД |
| uvicorn | 0.54.0 | BSD-3-Clause | ASGI-сервер |

## Бэкенд — транзитивные зависимости

| Библиотека | Версия | Лицензия |
|---|---|---|
| annotated-doc | 0.0.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.15.1 | MIT |
| ast_serialize | 0.11.2 | MIT |
| certifi | 2026.7.22 | Mozilla Public 2.0 (MPL 2.0) |
| click | 8.5.0 | BSD-3-Clause |
| et_xmlfile | 2.0.0 | MIT |
| greenlet | 3.5.6 | MIT AND PSF-2.0 |
| grimp | 3.17 | BSD |
| h11 | 0.16.0 | MIT |
| httpcore | 1.0.9 | BSD-3-Clause |
| httptools | 0.8.0 | MIT |
| idna | 3.20 | BSD-3-Clause |
| iniconfig | 2.3.0 | MIT |
| librt | 0.15.0 | MIT |
| Mako | 1.4.3 | MIT |
| markdown-it-py | 4.2.0 | MIT |
| MarkupSafe | 3.0.3 | BSD-3-Clause |
| mdurl | 0.1.2 | MIT |
| mypy_extensions | 1.1.0 | MIT |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| pathspec | 1.1.1 | Mozilla Public 2.0 (MPL 2.0) |
| pluggy | 1.6.0 | MIT |
| pydantic_core | 2.46.5 | MIT |
| Pygments | 2.21.0 | BSD-2-Clause |
| python-dotenv | 1.2.3 | BSD-3-Clause |
| rich | 15.0.0 | MIT |
| starlette | 1.7.0 | BSD-3-Clause |
| typing-inspection | 0.4.4 | MIT |
| typing_extensions | 4.16.0 | PSF-2.0 |
| uvloop | 0.22.1 | Apache-2.0; MIT |
| watchfiles | 1.3.0 | MIT |
| websockets | 17.1 | BSD-3-Clause |

## Фронтенд (Node 22)

| Библиотека | Версия | Лицензия | Пакет | Роль |
|---|---|---|---|---|
| @fontsource/roboto | 5.3.0 | OFL-1.1 | frontend | в поставке |
| @tanstack/react-query | 5.104.0 | MIT | frontend | в поставке |
| leaflet | 1.9.4 | BSD-2-Clause | frontend | в поставке |
| react | 18.3.1 | MIT | frontend | в поставке |
| react-dom | 18.3.1 | MIT | frontend | в поставке |
| react-router-dom | 6.30.6 | MIT | frontend | в поставке |
| @types/leaflet | 1.9.22 | MIT | frontend | сборка и проверка |
| @types/react | 18.3.31 | MIT | frontend | сборка и проверка |
| @types/react | 18.3.31 | MIT | packages | сборка и проверка |
| @types/react-dom | 18.3.7 | MIT | frontend | сборка и проверка |
| @vitejs/plugin-react | 4.7.0 | MIT | frontend | сборка и проверка |
| react | 18.3.1 | MIT | packages | сборка и проверка |
| react | 18.3.1 | MIT | packages | peer |
| typescript | 5.9.3 | Apache-2.0 | frontend | сборка и проверка |
| typescript | 5.9.3 | Apache-2.0 | packages | сборка и проверка |
| vite | 5.4.21 | MIT | frontend | сборка и проверка |

## Инструменты и образы (в поставку кода не входят)

pytest, pytest-asyncio, ruff, mypy, import-linter (Python); TypeScript, Vite (фронтенд). Контейнеры: `python:3.12-slim`, `node:22-alpine`, `nginx:1.27-alpine`, `postgres:16-alpine`, `ollama/ollama` — официальные образы с открытыми лицензиями.
