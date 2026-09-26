# Модуль `assessment`

Автооценка по эталону (правила + ИИ-судья), экспертная оценка, отчёты.

- **Пункты плана:** 3.4, 3.5, 4.3
- **Ключевые сценарии:** AssessAttempt, OverrideAssessment; GetSessionReport

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
