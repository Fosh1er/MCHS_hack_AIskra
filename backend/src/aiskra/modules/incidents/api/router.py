"""HTTP API карточки происшествия 112 (п. 1.1): открыть, сохранить, получить."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from aiskra.modules.incidents.api import deps
from aiskra.modules.incidents.api.schemas import (
    CardOpenedOut,
    CardSavedOut,
    CardServiceOut,
    OpenCardIn,
    SaveCardIn,
)
from aiskra.modules.incidents.application.commands.open_card import OpenCard, OpenCardHandler
from aiskra.modules.incidents.application.commands.save_card import SaveCard, SaveCardHandler
from aiskra.modules.incidents.application.ports.cards import CardView
from aiskra.modules.incidents.application.queries.get_card import GetCard, GetCardHandler
from aiskra.modules.incidents.domain.incident import AddedBy, CardService
from aiskra.shared.security import Permission, Principal
from aiskra.shared.web import CurrentPrincipal, Meta, require

router = APIRouter(prefix="/incidents", tags=["incidents"])
Trainee = Annotated[Principal, Depends(require(Permission.TRAINING_PARTICIPATE))]


@router.post("/cards", response_model=CardOpenedOut, status_code=201, summary="Открыть новую карточку (Insert)")
async def open_card(
    body: OpenCardIn,
    actor: Trainee,
    meta: Meta,
    handler: Annotated[OpenCardHandler, Depends(deps.provide_open_card)],
) -> CardOpenedOut:
    opened = await handler(OpenCard(actor=actor, aon=body.aon, channel=body.channel, meta=meta))
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
