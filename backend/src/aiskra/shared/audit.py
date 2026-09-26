"""Порт журнала аудита и каталог событий (п. 0.3, ADR-0010). Чистый Python — общий для всех модулей.

Модули не импортируют модуль `audit` (независимость модулей, ADR-0001): обработчик команды получает
`AuditRecorder` через конструктор и явно записывает событие (ADR-0002). Реализации — в
`modules/audit/infrastructure`, связывание — в composition root.

Колонки записи повторяют раздел «Аудит» АРМ-112 (`img/instr/image114.png`):
Карточка, Опер., ФИО оператора, Дата, Время, Событие, Описание.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from aiskra.shared.security import Principal


class AuditEvent(StrEnum):
    """Каталог событий. Новое значимое действие — новое значение здесь и название в `AUDIT_EVENT_TITLES`."""

    LOGIN_SUCCEEDED = "auth.login_succeeded"
    LOGIN_FAILED = "auth.login_failed"
    ACCOUNT_LOCKED = "auth.account_locked"
    LOGOUT = "auth.logout"
    ACCESS_DENIED = "auth.access_denied"
    USER_CREATED = "users.created"
    USER_UPDATED = "users.updated"
    USER_BLOCKED = "users.blocked"
    USER_UNBLOCKED = "users.unblocked"
    PASSWORD_RESET = "users.password_reset"
    DICTIONARIES_IMPORTED = "dictionaries.imported"
    ADDRESSES_IMPORTED = "dictionaries.addresses_imported"
    CARD_CREATED = "card.created"
    SERVICE_RECEIVED = "dds.received"
    SERVICE_STATUS_CHANGED = "dds.status_changed"
    CARD_SAVED = "card.saved"
    CARD_VIEWED = "card.viewed"
    CARD_WORKED = "card.worked"
    CARD_CHECKED = "card.checked"
    CARD_RETURNED = "card.returned"
    CARD_FLAGS = "card.flags"
    CARD_APPENDED = "card.appended"
    WORKOUT_ADDED = "card.workout_added"

    @property
    def label(self) -> str:
        return AUDIT_EVENT_TITLES[self]


AUDIT_EVENT_TITLES: Mapping[AuditEvent, str] = {
    AuditEvent.LOGIN_SUCCEEDED: "Вход в систему",
    AuditEvent.LOGIN_FAILED: "Неудачная попытка входа",
    AuditEvent.ACCOUNT_LOCKED: "Временная блокировка после неудачных попыток входа",
    AuditEvent.LOGOUT: "Выход из системы",
    AuditEvent.ACCESS_DENIED: "Отказ в доступе",
    AuditEvent.USER_CREATED: "Создание пользователя",
    AuditEvent.USER_UPDATED: "Изменение пользователя",
    AuditEvent.USER_BLOCKED: "Блокировка пользователя",
    AuditEvent.USER_UNBLOCKED: "Разблокировка пользователя",
    AuditEvent.PASSWORD_RESET: "Сброс пароля",
    AuditEvent.DICTIONARIES_IMPORTED: "Импорт справочников",
    AuditEvent.ADDRESSES_IMPORTED: "Импорт адресного справочника",
    AuditEvent.CARD_CREATED: "Создание карточки происшествия",
    AuditEvent.SERVICE_RECEIVED: "Карточка получена службой (ДДС)",
    AuditEvent.SERVICE_STATUS_CHANGED: "Изменение статуса службы (ДДС)",
    AuditEvent.CARD_SAVED: "Сохранение карточки происшествия",
    AuditEvent.CARD_VIEWED: "Просмотр карточки",
    AuditEvent.CARD_WORKED: "Переход в Отработана",
    AuditEvent.CARD_CHECKED: "Переход в Проверена",
    AuditEvent.CARD_RETURNED: "Возврат на доработку",
    AuditEvent.CARD_FLAGS: "Изменение признаков ЧС / ЧП",
    AuditEvent.CARD_APPENDED: "Дополнение карточки",
    AuditEvent.WORKOUT_ADDED: "Отработка",
}


@dataclass(frozen=True, kw_only=True)
class RequestMeta:
    """Откуда пришёл запрос. Заполняется в API, передаётся в команду для аудита."""

    ip: str | None = None
    user_agent: str | None = None


@dataclass(frozen=True, kw_only=True)
class AuditEntry:
    """Запись журнала. `actor=None` — действие системы или анонимного пользователя (неудачный вход, CLI)."""

    event: AuditEvent
    actor: Principal | None = None
    actor_login: str | None = None  # для анонимных событий: какой логин вводили
    description: str = ""
    card_number: int | None = None
    object_type: str | None = None
    object_id: str | None = None
    meta: RequestMeta = field(default_factory=RequestMeta)
    data: Mapping[str, Any] = field(default_factory=dict)


class AuditRecorder(Protocol):
    """Запись в журнал аудита. Журнал только дополняется: изменения и удаления записей нет."""

    async def record(self, entry: AuditEntry) -> None: ...
