"""HTTP-адаптер справочников. Ответы — DTO запросов (dataclass сериализуются FastAPI напрямую)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from aiskra.modules.dictionaries.api import deps
from aiskra.modules.dictionaries.application.commands.import_dictionaries import (
    ImportDictionaries,
    ImportDictionariesHandler,
    ImportReport,
)
from aiskra.modules.dictionaries.application.ports.reader import CardTypeRow, EnumValueRow, ServiceRow
from aiskra.modules.dictionaries.application.queries.incident_types import (
    GetIncidentType,
    GetIncidentTypeHandler,
    GetQuestionnaireTree,
    GetQuestionnaireTreeHandler,
    IncidentTypeDetails,
    IncidentTypePage,
    QuestionnaireTree,
    SearchCardTypes,
    SearchCardTypesHandler,
    SearchIncidentTypes,
    SearchIncidentTypesHandler,
)
from aiskra.modules.dictionaries.application.queries.reference import (
    ListEnum,
    ListEnumHandler,
    ListServices,
    ListServicesHandler,
    ListTerritory,
    ListTerritoryHandler,
    Territory,
)
from aiskra.shared.security import Permission, Principal
from aiskra.shared.web import Meta, require

router = APIRouter(
    prefix="/dictionaries", tags=["dictionaries"], dependencies=[Depends(require(Permission.DICTIONARIES_READ))]
)


@router.post("/import", response_model=ImportReport, summary="Импорт справочников из data/ (команда, п. 0.2)")
async def import_dictionaries(
    actor: Annotated[Principal, Depends(require(Permission.DICTIONARIES_IMPORT))],
    meta: Meta,
    handler: Annotated[ImportDictionariesHandler, Depends(deps.provide_import)],
) -> ImportReport:
    return await handler(ImportDictionaries(actor=actor, meta=meta))


@router.get("/card-types", response_model=list[CardTypeRow], summary="Типы «Что случилось?» с поиском по синонимам")
async def search_card_types(
    handler: Annotated[SearchCardTypesHandler, Depends(deps.provide_search_card_types)],
    q: str = "",
    quick: bool = False,
    significant: bool = False,
) -> list[CardTypeRow]:
    return await handler(SearchCardTypes(q=q, only_quick=quick, only_significant=significant))


@router.get(
    "/card-types/{code}/questionnaire",
    response_model=QuestionnaireTree,
    summary="Дерево опросной карты: признак 1 → 2 → 3 → конечные типы",
)
async def questionnaire(
    code: str,
    handler: Annotated[GetQuestionnaireTreeHandler, Depends(deps.provide_questionnaire)],
) -> QuestionnaireTree:
    return await handler(GetQuestionnaireTree(card_type=code))


@router.get("/incident-types", response_model=IncidentTypePage, summary="Поиск типов происшествий классификатора")
async def search_incident_types(
    handler: Annotated[SearchIncidentTypesHandler, Depends(deps.provide_search_incident_types)],
    q: str = "",
    group: Annotated[list[int] | None, Query()] = None,
    visible_only: bool = True,
    limit: int = 50,
    offset: int = 0,
) -> IncidentTypePage:
    return await handler(SearchIncidentTypes(q=q, groups=group, visible_only=visible_only, limit=limit, offset=offset))


@router.get(
    "/incident-types/{code}", response_model=IncidentTypeDetails, summary="Тип происшествия и строка матрицы служб"
)
async def get_incident_type(
    code: str,
    handler: Annotated[GetIncidentTypeHandler, Depends(deps.provide_get_incident_type)],
) -> IncidentTypeDetails:
    return await handler(GetIncidentType(code=code))


@router.get("/services", response_model=list[ServiceRow], summary="Справочник служб и ДДС")
async def list_services(
    handler: Annotated[ListServicesHandler, Depends(deps.provide_list_services)],
    q: str = "",
    kind: Annotated[list[str] | None, Query()] = None,
    okrug: str | None = None,
) -> list[ServiceRow]:
    return await handler(ListServices(q=q, kinds=kind, okrug=okrug))


@router.get("/territory", response_model=Territory, summary="Округа и районы (поселения) Москвы")
async def territory(
    handler: Annotated[ListTerritoryHandler, Depends(deps.provide_list_territory)],
    okrug: str | None = None,
    q: str = "",
) -> Territory:
    return await handler(ListTerritory(okrug=okrug, q=q))


@router.get(
    "/enums/{domain}",
    response_model=list[EnumValueRow],
    summary="Перечисления: applicant_status, card_status, service_status, telephony_status, card_flag, channel",
)
async def list_enum(
    domain: str, handler: Annotated[ListEnumHandler, Depends(deps.provide_list_enum)]
) -> list[EnumValueRow]:
    return await handler(ListEnum(domain=domain))
