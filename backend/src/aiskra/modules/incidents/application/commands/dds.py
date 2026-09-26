"""Команды АРМ ДДС (п. 2.2): «Получена службой» при открытии карточки и смена статуса своей службы.

Кто работает за ДДС, решает учебный процесс: обучающийся выбирает службу при входе в АРМ ДДС (позже — назначение
преподавателя, 4.2). Права проверяет API (`training.participate`), здесь — что служба есть в карточке и правила
переходов (`domain/dds.py`)."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from aiskra.modules.incidents.application.ports.dds import DdsRepository, DdsServiceState
from aiskra.modules.incidents.domain.dds import TITLES, ServiceStatus, check_transition
from aiskra.shared.application import Clock, Command, UnitOfWork
from aiskra.shared.audit import AuditEntry, AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.errors import NotFoundError
from aiskra.shared.security import Principal


async def load_state(repo: DdsRepository, card_id: UUID, service_code: str) -> DdsServiceState:
    """Карточка, не направленная в эту службу, или черновик 112 для ДДС «не существует»."""
    state = await repo.state(card_id, service_code)
    if state is None or state.card_status == "draft":
        raise NotFoundError("Карточка не поступала в эту службу", code="dds_card_not_found")
    return state


def _entry(
    event: AuditEvent, actor: Principal, st: DdsServiceState, meta: RequestMeta, text: str, data: dict[str, str]
) -> AuditEntry:
    return AuditEntry(
        event=event,
        actor=actor,
        card_number=st.card_number,
        description=f"{st.service_short}: {text}",
        object_type="card_service",
        object_id=f"{st.card_id}:{st.service_code}",
        meta=meta,
        data=data,
    )


class _Base:
    def __init__(self, repo: DdsRepository, audit: AuditRecorder, uow: UnitOfWork, clock: Clock) -> None:
        self._repo = repo
        self._audit = audit
        self._uow = uow
        self._clock = clock


@dataclass(frozen=True, kw_only=True)
class MarkServiceReceived(Command):
    actor: Principal
    card_id: UUID
    service_code: str
    meta: RequestMeta = field(default_factory=RequestMeta)


class MarkServiceReceivedHandler(_Base):
    """Идемпотентно: «Добавлена» → «Получена службой» при первом открытии карточки в ДДС (dds/image10)."""

    async def __call__(self, cmd: MarkServiceReceived) -> str:
        st = await load_state(self._repo, cmd.card_id, cmd.service_code)
        if st.current_status != ServiceStatus.ADDED:
            return st.current_status
        try:
            await self._repo.set_status(
                cmd.card_id,
                cmd.service_code,
                ServiceStatus.RECEIVED.value,
                order_no=None,
                comment=None,
                actor_id=cmd.actor.user_id,
                at=self._clock.now(),
            )
            await self._audit.record(
                _entry(AuditEvent.SERVICE_RECEIVED, cmd.actor, st, cmd.meta, TITLES[ServiceStatus.RECEIVED], {})
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return ServiceStatus.RECEIVED.value


@dataclass(frozen=True, kw_only=True)
class ChangeServiceStatus(Command):
    actor: Principal
    card_id: UUID
    service_code: str
    status: ServiceStatus
    order_no: str = ""
    comment: str = ""
    meta: RequestMeta = field(default_factory=RequestMeta)


class ChangeServiceStatusHandler(_Base):
    async def __call__(self, cmd: ChangeServiceStatus) -> str:
        st = await load_state(self._repo, cmd.card_id, cmd.service_code)
        order_no, comment = cmd.order_no.strip(), cmd.comment.strip()
        check_transition(ServiceStatus(st.current_status), cmd.status, order_no, comment)
        text = TITLES[cmd.status] + (f" · наряд {order_no}" if order_no else "") + (f" · {comment}" if comment else "")
        try:
            await self._repo.set_status(
                cmd.card_id,
                cmd.service_code,
                cmd.status.value,
                order_no=order_no or None,
                comment=comment or None,
                actor_id=cmd.actor.user_id,
                at=self._clock.now(),
            )
            await self._audit.record(
                _entry(
                    AuditEvent.SERVICE_STATUS_CHANGED,
                    cmd.actor,
                    st,
                    cmd.meta,
                    text,
                    {"from": st.current_status, "to": cmd.status.value},
                )
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return cmd.status.value
