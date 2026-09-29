"""Запросы звонков (п. 1.4, 2.3): звонок с репликами и журнал звонков по карточке (для ДДС и оценки 3.4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from aiskra.modules.training.application.ports.scenarios import CallRepository
from aiskra.modules.training.domain.call import Call, Speaker, call_mode
from aiskra.modules.training.domain.tone import ToneSnapshot
from aiskra.shared.application import Query
from aiskra.shared.errors import NotFoundError
from aiskra.shared.security import Permission, Principal


@dataclass(frozen=True)
class MessageView:
    speaker: str
    text: str
    at: datetime
    id: UUID | None = None
    tone: ToneSnapshot | None = None  # у реплик заявителя (п. 3.6)
    remarks: list[str] = field(default_factory=list)  # п. 3.7: ремарки заявителя
    meta: dict[str, Any] | None = None  # п. 3.7: действия оператора, уровень заявителя — для разбора


@dataclass(frozen=True)
class CallView:
    id: UUID
    role: str
    party: str
    direction: str
    status: str
    aon: str
    card_id: UUID | None
    service_code: str | None
    target_service: str | None
    started_at: datetime
    answered_at: datetime | None
    ended_at: datetime | None
    messages: list[MessageView]
    tone: ToneSnapshot | None = None  # текущее состояние заявителя (п. 3.6); у старшего группы и службы — нет
    mode: str | None = None  # как вёл разговор оператор: text | voice | hands_free (п. 3.6)
    ended_by: str | None = None
    psy: dict[str, Any] | None = None  # п. 3.7: профиль заявителя, старт, пик и текущий уровень


def call_visible(call: Call | None, actor: Principal) -> bool:
    return call is not None and (call.student_id == actor.user_id or actor.can(Permission.RESULTS_READ_ALL))


async def _view(repo: CallRepository, call: Call, with_messages: bool = True) -> CallView:
    messages = await repo.messages(call.id) if with_messages else []
    mode = call_mode([m.via for m in messages if m.speaker is Speaker.OPERATOR and m.via])
    return CallView(
        id=call.id,
        role=call.role,
        party=call.party.value,
        direction=call.direction,
        status=call.status.value,
        aon=call.aon,
        card_id=call.card_id,
        service_code=call.service_code,
        target_service=call.target_service,
        started_at=call.started_at,
        answered_at=call.answered_at,
        ended_at=call.ended_at,
        messages=[
            MessageView(
                speaker=m.speaker.value,
                text=m.text,
                at=m.at,
                id=m.id,
                tone=m.tone,
                remarks=list((m.meta or {}).get("remarks") or []),
                meta=m.meta,
            )
            for m in messages
        ],
        tone=call.tone.snapshot() if call.tone else None,
        mode=mode.value if mode else None,
        ended_by=call.ended_by,
        psy=_psy_summary(call.psy),
    )


def _psy_summary(psy: dict[str, Any] | None) -> dict[str, Any] | None:
    if not psy:
        return None
    state = psy.get("state") or {}
    return {
        "profile": psy.get("profile"),
        "title": psy.get("title"),
        "sensitive": psy.get("sensitive"),
        "start": psy.get("start"),
        "level": state.get("level"),
        "peak": state.get("peak"),
        "stage": state.get("stage"),
        "paused": psy.get("paused"),
        "hung_up": state.get("hung_up"),
    }


@dataclass(frozen=True, kw_only=True)
class GetCall(Query):
    actor: Principal
    call_id: UUID


class GetCallHandler:
    def __init__(self, repo: CallRepository) -> None:
        self._repo = repo

    async def __call__(self, q: GetCall) -> CallView:
        call = await self._repo.get(q.call_id)
        if call is None or not call_visible(call, q.actor):
            raise NotFoundError("Звонок не найден", code="call_not_found")
        return await _view(self._repo, call)


@dataclass(frozen=True, kw_only=True)
class CardCalls(Query):
    actor: Principal
    card_id: UUID


class CardCallsHandler:
    """Журнал звонков по карточке: свои — обучающемуся, все — преподавателю."""

    def __init__(self, repo: CallRepository) -> None:
        self._repo = repo

    async def __call__(self, q: CardCalls) -> list[CallView]:
        student = None if q.actor.can(Permission.RESULTS_READ_ALL) else q.actor.user_id
        calls = await self._repo.calls_of_card(q.card_id, student)
        return [await _view(self._repo, c) for c in calls]
