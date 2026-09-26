# Модуль `incidents`

Карточка происшествия 112, журнал; карточка и очередь ДДС, статусы реагирования.

- **Пункты плана:** 1.1–1.6, 2.1–2.4. Спецификация карточки — [specs/1.1](../../../../../specs/1.1-card-112.md).
- **Сделано (1.1):**
  - сущность `domain/incident.py` (`IncidentCard`, правила обязательных полей `missing_for_save`, пустая карточка → «Завершена»);
  - команды `OpenCard` (номер, таймер) и `SaveCard` (оповестить и сохранить, службы «Добавлена»), запрос `GetCard`;
  - API `/api/v1/incidents/cards`, `/cards/{id}/save`, `/cards/{id}`; аудит «Создание / Сохранение карточки».
- **Службы на карточку** присылает клиент: автоподбор — запрос `dictionaries.ResolveServices`, оператор мог убрать или добавить службу. Модуль не импортирует `dictionaries` (ADR-0001), связь — внешний ключ `card_services → dict_services`.
- **Дальше:** журнал и просмотр (1.3), входящий вызов (1.4), очередь ДДС (2.x).

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
