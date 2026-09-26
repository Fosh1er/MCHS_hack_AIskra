# Модуль `dictionaries`

Справочники: классификатор происшествий (ЕКП), службы и ДДС с телефонами, округа/районы, каналы связи, статусы заявителя/карточки/ДДС.

- **Пункты плана:** 0.2; автоподбор служб — основа 1.5 (используется карточкой 1.1)
- **Ключевые сценарии:** ImportDictionaries; SearchCardTypes, GetQuestionnaireTree, SearchIncidentTypes, GetIncidentType, ListServices, ListTerritory, ListEnum, **ResolveServices**
- **Правило матрицы служб** — `domain/routing.py` (чистая функция, тесты `unit/test_routing.py`); территориальные службы и главная служба — `application/queries/resolve_services.py`; API `GET /dictionaries/services/resolve`.

## Слои
| Папка | Что кладём | Можно импортировать |
|---|---|---|
| `domain/` | сущности, value objects, доменные сервисы, правила | только `aiskra.shared.domain`, stdlib |
| `application/commands/` | команда (dataclass) + обработчик, меняющий состояние | domain, `application/ports`, `aiskra.shared`, `aiskra.ai.ports/router/tasks` |
| `application/queries/` | запрос + DTO + обработчик/порт чтения | то же |
| `application/ports/` | Protocol-интерфейсы репозиториев и внешних сервисов | domain |
| `infrastructure/` | ORM-модели, репозитории, SQL-реализации запросов | всё, кроме `api` |
| `api/` | FastAPI-роутер, pydantic-схемы, `deps.py` с заглушками провайдеров | application, `aiskra.shared` |

Рецепты добавления команды, запроса и ИИ-задачи — в корневом `AGENTS.md`.
