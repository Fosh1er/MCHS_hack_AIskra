"""HTTP-адаптер справочников. Ответы — DTO запросов (dataclass сериализуются FastAPI напрямую)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from aiskra.modules.dictionaries.api import deps
from aiskra.modules.dictionaries.application.commands.import_addresses import (
    AddressImportReport,
    ImportAddresses,
    ImportAddressesHandler,
)
from aiskra.modules.dictionaries.application.commands.import_dictionaries import (
    ImportDictionaries,
    ImportDictionariesHandler,
    ImportReport,
)
from aiskra.modules.dictionaries.application.ports.reader import CardTypeRow, EnumValueRow, GroupRow, ServiceRow
from aiskra.modules.dictionaries.application.queries.addresses import (
    AddressSuggestion,
    DistrictShapes,
    DistrictShapesHandler,
    GeocodeResult,
    GeoCollection,
    HousePoint,
    HousesInBox,
    HousesInBoxHandler,
    ReverseGeocode,
    ReverseGeocodeHandler,
    SuggestAddresses,
    SuggestAddressesHandler,
)
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
    ListGroups,
    ListGroupsHandler,
    ListServices,
    ListServicesHandler,
    ListTerritory,
    ListTerritoryHandler,
    Territory,
)
from aiskra.modules.dictionaries.application.queries.resolve_services import (
    ResolvedServices,
    ResolveServices,
    ResolveServicesHandler,
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


@router.get("/incident-groups", response_model=list[GroupRow], summary="Группы классификатора (категории событий)")
async def list_groups(handler: Annotated[ListGroupsHandler, Depends(deps.provide_list_groups)]) -> list[GroupRow]:
    return await handler(ListGroups())


@router.get("/services", response_model=list[ServiceRow], summary="Справочник служб и ДДС")
async def list_services(
    handler: Annotated[ListServicesHandler, Depends(deps.provide_list_services)],
    q: str = "",
    kind: Annotated[list[str] | None, Query()] = None,
    okrug: str | None = None,
) -> list[ServiceRow]:
    return await handler(ListServices(q=q, kinds=kind, okrug=okrug))


@router.get(
    "/services/resolve",
    response_model=ResolvedServices,
    summary="Автоподбор служб карточки 112: типы классификатора + признаки + адрес (основа п. 1.5)",
)
async def resolve_services(
    handler: Annotated[ResolveServicesHandler, Depends(deps.provide_resolve_services)],
    incident_type: Annotated[list[str], Query(description="Конечные типы классификатора")],
    flag: Annotated[list[str] | None, Query(description="Признаки карточки (enums.card_flag)")] = None,
    okrug: str | None = None,
    district: str | None = None,
) -> ResolvedServices:
    return await handler(
        ResolveServices(incident_types=incident_type, flags=flag or [], okrug=okrug, district=district)
    )


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


# ------------------------------------------------------------------ п. 1.2: адресный справочник и карта


@router.post(
    "/addresses/import", response_model=AddressImportReport, summary="Импорт адресного справочника из data/ (п. 1.2)"
)
async def import_addresses(
    actor: Annotated[Principal, Depends(require(Permission.DICTIONARIES_IMPORT))],
    meta: Meta,
    handler: Annotated[ImportAddressesHandler, Depends(deps.provide_import_addresses)],
) -> AddressImportReport:
    return await handler(ImportAddresses(actor=actor, meta=meta))


@router.get(
    "/addresses/suggest",
    response_model=list[AddressSuggestion],
    summary="Подсказки единой адресной строки: улица → дома (instr/image20)",
)
async def suggest_addresses(
    handler: Annotated[SuggestAddressesHandler, Depends(deps.provide_suggest_addresses)],
    q: str,
    limit: int = 10,
) -> list[AddressSuggestion]:
    return await handler(SuggestAddresses(q=q, limit=limit))


@router.get(
    "/addresses/reverse",
    response_model=GeocodeResult,
    summary="Адрес и район по точке: «Указать на карте», ввод координат (instr/image27, image28)",
)
async def reverse_geocode(
    handler: Annotated[ReverseGeocodeHandler, Depends(deps.provide_reverse_geocode)],
    lat: float,
    lon: float,
) -> GeocodeResult:
    return await handler(ReverseGeocode(lat=lat, lon=lon))


@router.get("/addresses/houses", response_model=list[HousePoint], summary="Дома в окне карты (крупный масштаб)")
async def houses_in_box(
    handler: Annotated[HousesInBoxHandler, Depends(deps.provide_houses_in_box)],
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
) -> list[HousePoint]:
    return await handler(HousesInBox(min_lat=min_lat, min_lon=min_lon, max_lat=max_lat, max_lon=max_lon))


@router.get("/territory/shapes", response_model=GeoCollection, summary="Границы районов (GeoJSON) для окна карты")
async def district_shapes(
    handler: Annotated[DistrictShapesHandler, Depends(deps.provide_district_shapes)],
) -> GeoCollection:
    return await handler(DistrictShapes())
