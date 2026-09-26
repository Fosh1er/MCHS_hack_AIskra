# Модуль `identity`

Пользователи, роли, вход по логину, паролю и номеру АРМ, сессии, управление учётными записями.
Решение — [ADR-0010](../../../../../docs/adr/0010-auth-rbac-audit.md), спецификация — [specs/0.3](../../../../../specs/0.3-auth-rbac-audit.md).

- **Пункты плана:** 0.3, 5.2 (экран пользователей)
- **Команды:** `Login`, `Logout`, `CreateUser`, `UpdateUser`, `SetUserBlocked`, `ResetPassword`
- **Запросы:** `ResolveSession` (на каждом защищённом запросе), `ListUsers`
- **API:**
  - `/api/v1/auth/login` — публичный;
  - `/auth/logout`, `/auth/me`;
  - `/users` (GET, POST), `/users/{id}` (PATCH), `/users/{id}/block|unblock|password` — право `users.manage`.
- **Правила домена** (`domain/user.py`):
  - логин без учёта регистра;
  - пароль от 8 символов и не равен логину;
  - блокировка после N неудачных попыток;
  - нельзя заблокировать себя и оставить систему без активного администратора (`commands/_common.py`).
- **Адаптеры:** `infrastructure/security.py` (scrypt, токены), `repositories.py`, `reader.py`.

## Слои
| Папка | Что кладём | Можно импортировать |
|---|---|---|
| `domain/` | сущности, value objects, доменные сервисы, правила | только `aiskra.shared` (кроме `web`), stdlib |
| `application/commands/` | команда (dataclass) + обработчик, меняющий состояние | domain, `application/ports`, `aiskra.shared`, `aiskra.ai.ports/router/tasks` |
| `application/queries/` | запрос + DTO + обработчик/порт чтения | то же |
| `application/ports/` | Protocol-интерфейсы репозиториев и внешних сервисов | domain |
| `infrastructure/` | ORM-модели, репозитории, SQL-реализации запросов | всё, кроме `api` |
| `api/` | FastAPI-роутер, pydantic-схемы, `deps.py` с заглушками провайдеров | application, `aiskra.shared` |

Рецепты добавления команды, запроса и ИИ-задачи — в корневом `AGENTS.md`.
