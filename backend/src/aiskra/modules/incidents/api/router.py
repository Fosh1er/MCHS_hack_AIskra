"""HTTP API карточки происшествия 112 (п. 1.1): открыть, сохранить, получить."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from aiskra.modules.incidents.api import deps
from aiskra.modules.incidents.api.schemas import (
    AppendIn,
    CardFlagsIn,
    CardOpenedOut,
    CardSavedOut,
    CardServiceOut,
    ChangedOut,
    CreatedOut,
    OpenCardIn,
    SaveCardIn,
    ServiceStatusIn,
    StatusCommentIn,
    StatusOut,
    WorkoutIn,
)
from aiskra.modules.incidents.application.commands.add_workout import AddWorkout, AddWorkoutHandler
from aiskra.modules.incidents.application.commands.append_card import AppendCard, AppendCardHandler
from aiskra.modules.incidents.application.commands.change_card_status import (
    ChangeCardStatus,
    ChangeCardStatusHandler,
    StatusAction,
)
from aiskra.modules.incidents.application.commands.dds import (
    ChangeServiceStatus,
    ChangeServiceStatusHandler,
    MarkServiceReceived,
    MarkServiceReceivedHandler,
)
from aiskra.modules.incidents.application.commands.open_card import OpenCard, OpenCardHandler
from aiskra.modules.incidents.application.commands.record_card_view import RecordCardView, RecordCardViewHandler
from aiskra.modules.incidents.application.commands.save_card import SaveCard, SaveCardHandler
from aiskra.modules.incidents.application.commands.set_card_flags import SetCardFlags, SetCardFlagsHandler
from aiskra.modules.incidents.application.ports.cards import CardView
from aiskra.modules.incidents.application.queries.dds import (
    DdsCardView,
    DdsJournalPage,
    GetDdsCard,
    GetDdsCardHandler,
    SearchDdsJournal,
    SearchDdsJournalHandler,
)
from aiskra.modules.incidents.application.queries.get_card import GetCard, GetCardHandler
from aiskra.modules.incidents.application.queries.search_journal import JournalPage, SearchJournal, SearchJournalHandler
from aiskra.modules.incidents.domain.incident import AddedBy, Appendix, CardService
from aiskra.shared.security import Permission, Principal
from aiskra.shared.web import CurrentPrincipal, Meta, require

router = APIRouter(prefix="/incidents", tags=["incidents"])
Trainee = Annotated[Principal, Depends(require(Permission.TRAINING_PARTICIPATE))]
Checker = Annotated[Principal, Depends(require(Permission.CARDS_CHECK))]


@router.post("/cards", response_model=CardOpenedOut, status_code=201, summary="Открыть новую карточку (Insert)")
async def open_card(
    body: OpenCardIn,
    actor: Trainee,
    meta: Meta,
    handler: Annotated[OpenCardHandler, Depends(deps.provide_open_card)],
) -> CardOpenedOut:
    opened = await handler(
        OpenCard(
            actor=actor,
            aon=body.aon,
            channel=body.channel,
            scenario_id=body.scenario_id,
            session_id=body.session_id,
            meta=meta,
        )
    )
    return CardOpenedOut(id=opened.id, number=opened.number, opened_at=opened.opened_at)


@router.post("/cards/{card_id}/save", response_model=CardSavedOut, summary="Оповестить службы и сохранить (Alt+S)")
async def save_card(
    card_id: UUID,
    body: SaveCardIn,
    actor: Trainee,
    meta: Meta,
    handler: Annotated[SaveCardHandler, Depends(deps.provide_save_card)],
) -> CardSavedOut:
    services = [
        CardService(code=s.code, is_main=s.is_main, added_by=AddedBy(s.added_by), service_type=s.service_type)
        for s in body.services
    ]
    saved = await handler(
        SaveCard(actor=actor, card_id=card_id, data=body.data.model_dump(), services=services, meta=meta)
    )
    return CardSavedOut(
        id=saved.id,
        number=saved.number,
        status=saved.status.value,
        saved_at=saved.saved_at,
        processing_ms=saved.processing_ms,
        services=[CardServiceOut(**asdict(s)) for s in saved.services],
    )


@router.get("/cards/{card_id}", response_model=CardView, summary="Карточка: своя — обучающемуся, любая — преподавателю")
async def get_card(
    card_id: UUID,
    actor: CurrentPrincipal,
    handler: Annotated[GetCardHandler, Depends(deps.provide_get_card)],
) -> CardView:
    return await handler(GetCard(actor=actor, card_id=card_id))


# ------------------------------------------------------------------ п. 1.3: журнал и работа с сохранённой карточкой


@router.get(
    "/journal", response_model=JournalPage, summary="«Список происшествий»: свои — обучающемуся, все — преподавателю"
)
async def journal(
    actor: CurrentPrincipal,
    handler: Annotated[SearchJournalHandler, Depends(deps.provide_search_journal)],
    q: str = "",
    status: Annotated[
        list[str] | None, Query(description="draft, registered, not_notified, worked, checked, completed")
    ] = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = 1,
    page_size: int = 15,
) -> JournalPage:
    return await handler(
        SearchJournal(
            actor=actor,
            q=q,
            statuses=status or [],
            date_from=date_from,
            date_to=date_to,
            page=page,
            page_size=page_size,
        )
    )


@router.post(
    "/cards/{card_id}/viewed", status_code=204, summary="Отметить открытие карточки в аудите («Просмотр карточки»)"
)
async def viewed(
    card_id: UUID,
    actor: CurrentPrincipal,
    meta: Meta,
    handler: Annotated[RecordCardViewHandler, Depends(deps.provide_record_view)],
) -> None:
    await handler(RecordCardView(actor=actor, card_id=card_id, meta=meta))


async def _status(
    handler: ChangeCardStatusHandler,
    actor: Principal,
    card_id: UUID,
    action: StatusAction,
    body: StatusCommentIn,
    meta: Meta,
) -> StatusOut:
    status = await handler(
        ChangeCardStatus(actor=actor, card_id=card_id, action=action, comment=body.comment, meta=meta)
    )
    return StatusOut(status=status)


@router.post("/cards/{card_id}/worked", response_model=StatusOut, summary="«отработана» (Alt+S в просмотре) — автор")
async def worked(
    card_id: UUID,
    body: StatusCommentIn,
    actor: Trainee,
    meta: Meta,
    handler: Annotated[ChangeCardStatusHandler, Depends(deps.provide_change_status)],
) -> StatusOut:
    return await _status(handler, actor, card_id, StatusAction.WORKED, body, meta)


@router.post("/cards/{card_id}/checked", response_model=StatusOut, summary="«Проверена» (Alt+Y) — преподаватель")
async def checked(
    card_id: UUID,
    body: StatusCommentIn,
    actor: Checker,
    meta: Meta,
    handler: Annotated[ChangeCardStatusHandler, Depends(deps.provide_change_status)],
) -> StatusOut:
    return await _status(handler, actor, card_id, StatusAction.CHECKED, body, meta)


@router.post(
    "/cards/{card_id}/returned", response_model=StatusOut, summary="«Вернуть на доработку» (Alt+N) — преподаватель"
)
async def returned(
    card_id: UUID,
    body: StatusCommentIn,
    actor: Checker,
    meta: Meta,
    handler: Annotated[ChangeCardStatusHandler, Depends(deps.provide_change_status)],
) -> StatusOut:
    return await _status(handler, actor, card_id, StatusAction.RETURNED, body, meta)


@router.post("/cards/{card_id}/flags", response_model=ChangedOut, summary="Признаки ЧС / ЧП")
async def flags(
    card_id: UUID,
    body: CardFlagsIn,
    actor: Trainee,
    meta: Meta,
    handler: Annotated[SetCardFlagsHandler, Depends(deps.provide_set_flags)],
) -> ChangedOut:
    changed = await handler(
        SetCardFlags(actor=actor, card_id=card_id, emergency=body.emergency, incident=body.incident, meta=meta)
    )
    return ChangedOut(changed=changed)


@router.post(
    "/cards/{card_id}/append", response_model=ChangedOut, summary="«дополнение» (Shift+F2): только пустые поля"
)
async def append(
    card_id: UUID,
    body: AppendIn,
    actor: Trainee,
    meta: Meta,
    handler: Annotated[AppendCardHandler, Depends(deps.provide_append)],
) -> ChangedOut:
    appendix = Appendix(fields=body.fields, description_add=body.description_add, victims_count=body.victims_count)
    return ChangedOut(changed=await handler(AppendCard(actor=actor, card_id=card_id, appendix=appendix, meta=meta)))


@router.post(
    "/cards/{card_id}/workouts", response_model=CreatedOut, status_code=201, summary="Отработка — звонок в службу"
)
async def add_workout(
    card_id: UUID,
    body: WorkoutIn,
    actor: Trainee,
    meta: Meta,
    handler: Annotated[AddWorkoutHandler, Depends(deps.provide_add_workout)],
) -> CreatedOut:
    workout_id = await handler(AddWorkout(actor=actor, card_id=card_id, meta=meta, **body.model_dump()))
    return CreatedOut(id=workout_id)


# ------------------------------------------------------------------ п. 2.1, 2.2: АРМ ДДС


@router.get(
    "/dds/{service_code}/journal",
    response_model=DdsJournalPage,
    summary="Реестр ДДС «Список происшествий»: карточки, поступившие в службу (dds/image3)",
)
async def dds_journal(
    service_code: str,
    actor: CurrentPrincipal,
    handler: Annotated[SearchDdsJournalHandler, Depends(deps.provide_dds_journal)],
    q: str = "",
    status: Annotated[list[str] | None, Query(description="Статусы службы (enums.service_status)")] = None,
    page: int = 1,
    page_size: int = 10,
) -> DdsJournalPage:
    return await handler(
        SearchDdsJournal(
            actor=actor, service_code=service_code, q=q, statuses=status or [], page=page, page_size=page_size
        )
    )


@router.get(
    "/dds/{service_code}/cards/{card_id}",
    response_model=DdsCardView,
    summary="Карточка глазами ДДС: содержимое, своя служба, доступные статусы",
)
async def dds_card(
    service_code: str,
    card_id: UUID,
    actor: CurrentPrincipal,
    handler: Annotated[GetDdsCardHandler, Depends(deps.provide_dds_card)],
) -> DdsCardView:
    return await handler(GetDdsCard(actor=actor, card_id=card_id, service_code=service_code))


@router.post(
    "/dds/{service_code}/cards/{card_id}/received",
    response_model=StatusOut,
    summary="«Получена службой» — при первом открытии карточки в ДДС",
)
async def dds_received(
    service_code: str,
    card_id: UUID,
    actor: Trainee,
    meta: Meta,
    handler: Annotated[MarkServiceReceivedHandler, Depends(deps.provide_dds_received)],
) -> StatusOut:
    return StatusOut(
        status=await handler(MarkServiceReceived(actor=actor, card_id=card_id, service_code=service_code, meta=meta))
    )


@router.post(
    "/dds/{service_code}/cards/{card_id}/status",
    response_model=StatusOut,
    summary="Статус своей службы: Принята / Не принята → … → Работы завершены (карандаш, dds/image8)",
)
async def dds_status(
    service_code: str,
    card_id: UUID,
    body: ServiceStatusIn,
    actor: Trainee,
    meta: Meta,
    handler: Annotated[ChangeServiceStatusHandler, Depends(deps.provide_dds_status)],
) -> StatusOut:
    status = await handler(
        ChangeServiceStatus(
            actor=actor,
            card_id=card_id,
            service_code=service_code,
            status=body.status,
            order_no=body.order_no,
            comment=body.comment,
            meta=meta,
        )
    )
    return StatusOut(status=status)
