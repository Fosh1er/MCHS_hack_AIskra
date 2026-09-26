# Модуль `audit`

Журнал аудита значимых действий. Колонки — как в разделе «Аудит» АРМ-112 (`image114.png`): Карточка, Опер., ФИО, Дата, Время, Событие, Описание.
Решение — [ADR-0010](../../../../../docs/adr/0010-auth-rbac-audit.md).

- **Пункты плана:** 0.3, 5.2
- **Запись:** другие модули пишут через порт `aiskra.shared.audit.AuditRecorder`, этот модуль они не импортируют.
  - `SqlAuditRecorder` — в транзакции команды;
  - `IsolatedAuditRecorder` — отдельной транзакцией (отказ в доступе).
- **Каталог событий:** `aiskra.shared.audit.AuditEvent` + `AUDIT_EVENT_TITLES`.
- **Запросы:** `SearchAudit` (текст по оператору / по карточке, тип, период, 15/30/50/100 на странице), `ListEventTypes`.
- **API:** `GET /api/v1/audit`, `GET /api/v1/audit/event-types` — право `audit.read`. Методов изменения и удаления нет: журнал только дополняется.
- **Хранение:** записи не удаляются приложением (ТЗ: не меньше 6 месяцев). Индексы: `at`, `event`, `card_number`, `actor_id`, `actor_login`.

## Слои
| Папка | Что кладём | Можно импортировать |
|---|---|---|
| `domain/` | сущности, value objects, доменные сервисы, правила | только `aiskra.shared` (кроме `web`), stdlib |
| `application/commands/` | команда (dataclass) + обработчик, меняющий состояние | domain, `application/ports`, `aiskra.shared`, `aiskra.ai.ports/router/tasks` |
| `application/queries/` | запрос + DTO + обработчик/порт чтения | то же |
| `application/ports/` | Protocol-интерфейсы репозиториев и внешних сервисов | domain |
| `infrastructure/` | ORM-модели, репозитории, SQL-реализации запросов | всё, кроме `api` |
| `api/` | FastAPI-роутер, pydantic-схемы, `deps.py` с заглушками провайдеров | application, `aiskra.shared` |
