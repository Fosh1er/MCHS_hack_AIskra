"""Работа диспетчера ДДС со статусом своей службы по карточке (п. 2.2).

Источник правил: скриншоты АРМ ДДС (data/source/screenshots/dds/image8–20.png) и ответы заказчика #684, #691, #739:
- первый статус — выбор из двух: «Принята» / «Не принята»;
- далее через карандаш: «Начало реагирования» → «Прибытие» → «Проведение работ» → «Работы завершены»;
  «Отказ от выполнения работ» — на любом шаге после принятия;
- «Добавлена» (карточка сохранена в 112) и «Получена службой» (ДДС открыла карточку) ставит система;
- диспетчер ДДС не правит содержимое карточки и не добавляет службы (#701, #739), алгоритм один для всех служб (#684).
"""

from __future__ import annotations

from enum import StrEnum

from aiskra.shared.errors import DomainError


class ServiceStatus(StrEnum):
    ADDED = "added"
    RECEIVED = "received"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    RESPONSE_STARTED = "response_started"
    ARRIVED = "arrived"
    WORKS_IN_PROGRESS = "works_in_progress"
    WORKS_COMPLETED = "works_completed"
    WORKS_REFUSED = "works_refused"


S = ServiceStatus
# Как в выпадающем списке «Статус» АРМ ДДС (dds/image14): после «Начала реагирования» — «Прибытие»,
# «Отказ от выполнения работ», «Работы завершены».
NEXT: dict[ServiceStatus, tuple[ServiceStatus, ...]] = {
    S.ADDED: (S.ACCEPTED, S.REJECTED),
    S.RECEIVED: (S.ACCEPTED, S.REJECTED),
    S.ACCEPTED: (S.RESPONSE_STARTED, S.WORKS_REFUSED, S.WORKS_COMPLETED),
    S.RESPONSE_STARTED: (S.ARRIVED, S.WORKS_REFUSED, S.WORKS_COMPLETED),
    S.ARRIVED: (S.WORKS_IN_PROGRESS, S.WORKS_REFUSED, S.WORKS_COMPLETED),
    S.WORKS_IN_PROGRESS: (S.WORKS_COMPLETED, S.WORKS_REFUSED),
    S.REJECTED: (),
    S.WORKS_COMPLETED: (),
    S.WORKS_REFUSED: (),
}
FINAL = frozenset({S.REJECTED, S.WORKS_COMPLETED, S.WORKS_REFUSED})
WAITING = frozenset({S.ADDED.value, S.RECEIVED.value})  # решения ещё нет — идёт таймер ожидания (норматив 30 с)
TITLES: dict[ServiceStatus, str] = {
    S.ADDED: "Добавлена",
    S.RECEIVED: "Получена службой",
    S.ACCEPTED: "Принята",
    S.REJECTED: "Не принята",
    S.RESPONSE_STARTED: "Начало реагирования",
    S.ARRIVED: "Прибытие",
    S.WORKS_IN_PROGRESS: "Проведение работ",
    S.WORKS_COMPLETED: "Работы завершены",
    S.WORKS_REFUSED: "Отказ от выполнения работ",
}
ORDER_NO_MAX, COMMENT_MAX = 32, 500
BRIGADES_MAX = 10  # сил на один вызов — больше в учебной карточке не бывает, защита от мусора


def next_statuses(current: ServiceStatus) -> list[ServiceStatus]:
    return list(NEXT[current])


def check_transition(current: ServiceStatus, new: ServiceStatus, order_no: str, comment: str) -> None:
    """Переход разрешён списком оригинала. «Принята» — с номером наряда и комментарием (что направлено),
    «Не принята» и «Отказ от выполнения работ» — с комментарием-причиной (enums.service_status.needs)."""
    if new not in NEXT[current]:
        allowed = ", ".join(TITLES[s] for s in NEXT[current]) or "нет — статус окончательный"
        raise DomainError(
            f"Из статуса «{TITLES[current]}» нельзя перейти в «{TITLES[new]}». Доступно: {allowed}",
            code="bad_service_transition",
        )
    if len(order_no) > ORDER_NO_MAX or len(comment) > COMMENT_MAX:
        raise DomainError("Слишком длинный номер наряда или комментарий", code="too_long")
    if new is S.ACCEPTED and not order_no.strip():
        raise DomainError("Для «Принята» укажите номер наряда", code="order_no_required")
    if new in (S.ACCEPTED, S.REJECTED, S.WORKS_REFUSED) and not comment.strip():
        raise DomainError(f"Для «{TITLES[new]}» нужен комментарий", code="comment_required")


def call_sign(brigade_code: str) -> str:
    """Позывной из ключа справочника «<служба>:<позывной>» (п. 5.5)."""
    return brigade_code.split(":", 1)[-1]


def check_brigades(
    service_code: str, new: ServiceStatus, chosen: list[str], known: set[str], busy: dict[str, int]
) -> None:
    """Ручной выбор сил своей службы (п. 5.5, #684): только бригады справочника своей службы, не занятые на другой
    незакрытой карточке; при «Не принята» силы не направляются. `busy` — бригада → номер карточки, где она работает."""
    if not chosen:
        return
    if new is S.REJECTED:
        raise DomainError("При «Не принята» силы не направляются", code="brigades_on_reject")
    if len(chosen) > BRIGADES_MAX or len(set(chosen)) != len(chosen):
        raise DomainError(f"Выберите до {BRIGADES_MAX} разных бригад", code="bad_brigades")
    foreign = [call_sign(b) for b in chosen if b not in known or not b.startswith(f"{service_code}:")]
    if foreign:
        raise DomainError(f"Нет в справочнике сил службы: {', '.join(foreign)}", code="unknown_brigade")
    taken = [f"{call_sign(b)} (карточка № {busy[b]})" for b in chosen if b in busy]
    if taken:
        raise DomainError(f"Бригада уже работает по другой карточке: {', '.join(taken)}", code="brigade_busy")
