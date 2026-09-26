"""Команда: импорт справочников (классификатор xlsx + выверенные YAML) в хранилище. Пункт плана 0.2.

Импорт идемпотентен: повторный запуск с теми же файлами даёт то же состояние.
Нарушения структуры (заголовки колонок, ссылки на неизвестные службы и признаки) — ошибка;
особенности данных заказчика (опечатки, пустые ячейки) — предупреждения в отчёте.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from aiskra.modules.dictionaries.application.ports.sources import (
    ClassifierSheet,
    ClassifierSource,
    CuratedDictionaries,
    CuratedSource,
    DictionaryPayload,
    DictionaryWriter,
)
from aiskra.modules.dictionaries.domain.model import (
    HIDDEN_FROM_112,
    TERRITORIAL_SERVICES,
    DeliveryKind,
    IncidentCode,
    IncidentType,
    ServiceColumn,
    clean,
    is_valid_scenario_code,
    parse_delivery,
    parse_main_services,
    search_form,
)
from aiskra.shared.application import Command, UnitOfWork
from aiskra.shared.audit import AuditEntry, AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.errors import DomainError
from aiskra.shared.security import Principal

FIRST_ROUTING_COL, LAST_ROUTING_COL = 15, 90  # Excel-колонки матрицы служб (с 1)


@dataclass(frozen=True, kw_only=True)
class ImportDictionaries(Command):
    actor: Principal | None = None  # None — CLI (от имени системы)
    meta: RequestMeta = field(default_factory=RequestMeta)


@dataclass
class ImportReport:
    source_file: str
    source_sha256: str
    counts: dict[str, int] = field(default_factory=dict)
    deactivated: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def synthetic_phone(code: str) -> str:
    """Детерминированный учебный номер: реальные телефоны служб в тренажёр не попадают (152-ФЗ)."""
    n = int(hashlib.sha256(code.encode()).hexdigest(), 16) % 10_000
    return f"+7 (495) 000-{n // 100:02d}-{n % 100:02d}"


def parse_sheet(sheet: ClassifierSheet, warnings: list[str]) -> tuple[dict[int, str], list[IncidentType]]:
    types: list[IncidentType] = []
    card112_spellings: Counter[str] = Counter()
    for row in sheet.rows:
        code = IncidentCode(str(row[4]).strip())
        group_id = int(row[0])
        if code.group != group_id:
            raise DomainError(f"Код {code.value} не соответствует группе {group_id}", code="bad_incident_code")
        routing = {}
        for col in range(FIRST_ROUTING_COL, LAST_ROUTING_COL + 1):
            raw = row[col - 1] if col - 1 < len(row) else None
            delivery = parse_delivery(raw)
            if delivery is None:
                continue
            if delivery.kind is DeliveryKind.CARD_112 and str(clean(raw)).lower() != "карточка-112":
                card112_spellings[str(clean(raw))] += 1
            routing[col] = delivery
        sign1 = clean(row[6])
        types.append(
            IncidentType(
                code=code,
                group_id=group_id,
                sign1=sign1,
                sign2=clean(row[7]),
                sign3=clean(row[8]),
                operator_hint=clean(row[9]),
                final_type=clean(row[10]),
                ekp_type=clean(row[11]),
                response_scenario=clean(row[12]),
                main_services=parse_main_services(row[13]),
                visible_to_112=not (sign1 and sign1.lower() == HIDDEN_FROM_112),
                routing=routing,
            )
        )
    groups = dict(sheet.group_titles)
    missing = sorted({t.group_id for t in types} - set(groups))
    if missing:
        warnings.append(
            f"В классификаторе нет строк-заголовков для групп {missing} — названия взяты из card_types.yaml"
        )
    bad_scn = [t.code.value for t in types if not is_valid_scenario_code(t.response_scenario)]
    if bad_scn:
        warnings.append(
            f"Типов с нестандартным или пустым «Сценарием реагирования»: {len(bad_scn)} (например {bad_scn[:3]})"
        )
    no_main = sum(1 for t in types if not t.main_services)
    if no_main:
        warnings.append(f"Типов без «Главной службы»: {no_main}")
    hidden = sum(1 for t in types if not t.visible_to_112)
    if hidden:
        warnings.append(
            f"Типов с пометкой «Не отображается оператору 112» (не показываются в опросной карте): {hidden}"
        )
    if card112_spellings:
        warnings.append(f"Нормализованы варианты написания «карточка-112»: {dict(card112_spellings)}")
    return groups, types


def validate_columns(sheet: ClassifierSheet, curated: CuratedDictionaries) -> list[ServiceColumn]:
    services = {s["code"] for s in curated.services} | TERRITORIAL_SERVICES
    flags = {f["code"] for f in curated.enums.get("card_flag", [])}
    columns: list[ServiceColumn] = []
    for c in curated.columns:
        col = ServiceColumn(
            col=int(c["col"]),
            service=c["service"],
            header=c["header"],
            recipient=c.get("recipient"),
            flag=c.get("flag"),
            base=c.get("base"),
            audience=c.get("audience", "card"),
        )
        actual = search_form(sheet.column_headers.get(col.col, ""))
        if search_form(col.header) not in actual:
            raise DomainError(
                f"Колонка {col.col}: ожидался заголовок «{col.header}», в файле «{actual}»",
                code="classifier_layout_changed",
            )
        if col.service not in services:
            raise DomainError(f"Колонка {col.col}: неизвестная служба {col.service}", code="unknown_service")
        if col.flag and col.flag not in flags:
            raise DomainError(f"Колонка {col.col}: неизвестный признак {col.flag}", code="unknown_flag")
        columns.append(col)
    expected = set(range(FIRST_ROUTING_COL, LAST_ROUTING_COL + 1))
    if {c.col for c in columns} != expected:
        raise DomainError("classifier_columns.yaml должен описывать все колонки 15–90", code="columns_incomplete")
    return columns


def validate_references(
    curated: CuratedDictionaries, groups: dict[int, str], types: list[IncidentType], warnings: list[str]
) -> None:
    okrugs = {o["code"] for o in curated.okrugs}
    services = {s["code"] for s in curated.services}
    dup = [c for c, n in Counter(s["code"] for s in curated.services).items() if n > 1]
    if dup:
        raise DomainError(f"Дублирующиеся коды служб: {dup}", code="duplicate_service")
    for d in curated.districts:
        if d["okrug"] not in okrugs or d["dds"] not in services:
            raise DomainError(f"Район {d['name']}: неизвестный округ или ДДС", code="bad_district")
    for s in curated.services:
        if s.get("okrug") and s["okrug"] not in okrugs:
            raise DomainError(f"Служба {s['code']}: неизвестный округ {s['okrug']}", code="bad_service")
    sign1_by_group: dict[int, set[str]] = {}
    for t in types:
        if t.sign1:
            sign1_by_group.setdefault(t.group_id, set()).add(search_form(t.sign1))
    for ct in curated.card_types:
        g = ct.get("group")
        if g is None:
            continue
        if g not in {t.group_id for t in types}:
            raise DomainError(f"Тип «{ct['title']}»: в классификаторе нет группы {g}", code="bad_card_type")
        for s1 in ct.get("sign1", []):
            if search_form(s1) not in sign1_by_group.get(g, set()):
                warnings.append(f"Тип «{ct['title']}»: признак «{s1}» не найден в группе {g}")
        groups.setdefault(g, ct["title"])
    known_main = {m for s in curated.services for m in s.get("main_codes", [])}
    unknown_main = sorted({m for t in types for m in t.main_services} - known_main)
    if unknown_main:
        warnings.append(f"Коды «Главной службы» без соответствия в services: {unknown_main}")


def build_services(curated: CuratedDictionaries) -> list[dict[str, Any]]:
    out = []
    for s in curated.services:
        out.append(
            {
                **s,
                "phone": s.get("phone") or synthetic_phone(s["code"]),
                "phone_synthetic": not s.get("phone"),
                "confirmed": s.get("confirmed", True),
                "integrated": s.get("integrated", True),
                "source": s.get("source", "customer_screenshot"),
            }
        )
    return out


class ImportDictionariesHandler:
    def __init__(
        self,
        classifier: ClassifierSource,
        curated: CuratedSource,
        writer: DictionaryWriter,
        audit: AuditRecorder,
        uow: UnitOfWork,
    ) -> None:
        self._classifier = classifier
        self._curated = curated
        self._writer = writer
        self._audit = audit
        self._uow = uow

    async def __call__(self, cmd: ImportDictionaries) -> ImportReport:
        warnings: list[str] = []
        sheet = self._classifier.read()
        curated = self._curated.read()
        groups, types = parse_sheet(sheet, warnings)
        columns = validate_columns(sheet, curated)
        validate_references(curated, groups, types, warnings)
        payload = DictionaryPayload(
            source_file=sheet.file_name,
            source_sha256=sheet.file_sha256,
            groups=groups,
            incident_types=types,
            columns=columns,
            services=build_services(curated),
            okrugs=curated.okrugs,
            districts=curated.districts,
            enums=curated.enums,
            channels=curated.channels,
            card_types=curated.card_types,
        )
        try:
            stats = await self._writer.replace(payload)
            await self._audit.record(
                AuditEntry(
                    event=AuditEvent.DICTIONARIES_IMPORTED,
                    actor=cmd.actor,
                    description=f"{sheet.file_name}: {stats.counts.get('incident_types', 0)} типов, "
                    f"{stats.counts.get('services', 0)} служб, предупреждений {len(warnings)}",
                    meta=cmd.meta,
                    data={"sha256": sheet.file_sha256, "counts": stats.counts},
                )
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return ImportReport(
            source_file=sheet.file_name,
            source_sha256=sheet.file_sha256,
            counts=stats.counts,
            deactivated=stats.deactivated,
            warnings=warnings,
        )
