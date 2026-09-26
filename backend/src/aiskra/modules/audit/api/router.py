"""HTTP API журнала аудита (администратор). Записи не меняются; удаляются только старше срока хранения (6.2)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends

from aiskra.modules.audit.api import deps
from aiskra.modules.audit.application.commands.purge import PurgeAudit, PurgeAuditHandler, PurgeResult
from aiskra.modules.audit.application.queries.search_audit import (
    AuditPage,
    EventType,
    ListEventTypes,
    ListEventTypesHandler,
    SearchAudit,
    SearchAuditHandler,
)
from aiskra.shared.security import Permission, Principal
from aiskra.shared.web import Meta, require

router = APIRouter(prefix="/audit", tags=["audit"], dependencies=[Depends(require(Permission.AUDIT_READ))])


@router.get("", response_model=AuditPage, summary="Поиск событий: текст, по оператору/карточке, тип, период")
async def search_audit(
    handler: Annotated[SearchAuditHandler, Depends(deps.provide_search_audit)],
    q: str = "",
    by_operator: bool = True,
    by_card: bool = True,
    event: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = 1,
    page_size: int = 15,
) -> AuditPage:
    return await handler(
        SearchAudit(
            q=q,
            by_operator=by_operator,
            by_card=by_card,
            event=event,
            date_from=date_from,
            date_to=date_to,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/event-types", response_model=list[EventType], summary="Каталог типов событий")
async def event_types(handler: Annotated[ListEventTypesHandler, Depends(deps.provide_event_types)]) -> list[EventType]:
    return await handler(ListEventTypes())


@router.post("/purge", response_model=PurgeResult, summary="Удалить записи старше срока хранения (не меньше 183 дней)")
async def purge_audit(
    actor: Annotated[Principal, Depends(require(Permission.SYSTEM_MANAGE))],
    meta: Meta,
    handler: Annotated[PurgeAuditHandler, Depends(deps.provide_purge)],
    dry_run: bool = False,
) -> PurgeResult:
    return await handler(PurgeAudit(actor=actor, dry_run=dry_run, meta=meta))
