"""SQL-чтение карточек: журнал «Список происшествий» (п. 1.3) и просмотр карточки.

Названия служб, округов, районов, типов классификатора и авторов берутся из таблиц других модулей через
лёгкие `table()`-описания: модуль не импортирует чужие ORM-модели (ADR-0001), связь на уровне БД задана
внешними ключами.

«Не оповещено» — вычисляемый статус: у зарегистрированной или отработанной карточки есть служба без
интеграции (`dict_services.integrated = false`), по которой нет отработки (specs/1.3 §2).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, DateTime, and_, case, column, exists, func, or_, select, table
from sqlalchemy.ext.asyncio import AsyncSession

from aiskra.modules.incidents.application.ports.cards import (
    CardServiceView,
    CardView,
    IncidentTypeInfo,
    JournalFilter,
    JournalRow,
    ReworkNote,
    StatusHistoryItem,
    WorkoutView,
)
from aiskra.modules.incidents.infrastructure.models import CardServiceModel as CS
from aiskra.modules.incidents.infrastructure.models import CardServiceStatusModel
from aiskra.modules.incidents.infrastructure.models import CardWorkoutModel as W
from aiskra.modules.incidents.infrastructure.models import IncidentCardModel as C
from aiskra.platform.types import as_utc
from aiskra.shared.text import search_key

_services = table("dict_services", column("code"), column("short_name"), column("integrated"))
_users = table("users", column("id"), column("full_name"), column("search_key"), column("operator_number"))
_okrugs = table("dict_okrugs", column("code"), column("short"))
_districts = table("dict_districts", column("code"), column("name"))
_types = table("dict_incident_types", column("code"), column("final_type"), column("ekp_type"))
# журнал аудита — источник комментария «Вернуть на доработку» (1.3 → 5.1): отдельного поля у карточки нет
_audit = table(
    "audit_log",
    column("id"),
    column("at", DateTime(timezone=True)),
    column("card_number"),
    column("event"),
    column("description"),
    column("actor_name"),
)

_unnotified = exists(
    select(1)
    .select_from(CS.__table__.join(_services, _services.c.code == CS.service_code))
    .where(
        CS.card_id == C.id,
        _services.c.integrated.is_(False),
        # корреляция — со строкой card_services уровнем выше (а не с incident_cards через уровень): иначе
        # SQLAlchemy добавляет incident_cards в FROM подзапроса, и отработка в одной карточке «оповещает» все (6.1)
        ~exists(select(1).where(W.card_id == CS.card_id, W.service_code == CS.service_code)),
    )
)
DISPLAY_STATUS = case(
    (and_(C.status.in_(("registered", "worked")), _unnotified), "not_notified"),
    else_=C.status,
)
# «Дата регистрации» = opened_at (миграция 0011 заполнила пустые из created_at): сортировка идёт по индексу
_REGISTERED_AT = C.opened_at


def _address(line: str | None, okrug: str | None, district: str | None) -> str | None:
    """«г. Москва, ул. Ивана Сусанина, 3, (САО, Западное Дегунино)» — как в журнале оригинала."""
    place = ", ".join(x for x in (okrug, district) if x)
    if not line:
        return f"({place})" if place else None
    return f"{line}, ({place})" if place else line


class SqlCardReader:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ------------------------------------------------------------------ журнал

    async def search(self, flt: JournalFilter) -> tuple[list[JournalRow], int]:
        conditions: list[ColumnElement[bool]] = []
        if flt.author_id is not None:
            conditions.append(C.author_id == flt.author_id)
        if flt.q:
            pattern = f"%{search_key(flt.q)}%"
            conditions.append(or_(C.search_key.like(pattern), _users.c.search_key.like(pattern)))
        if flt.date_from:
            conditions.append(flt.date_from <= _REGISTERED_AT)
        if flt.date_to:
            conditions.append(flt.date_to >= _REGISTERED_AT)
        if flt.statuses:
            conditions.append(DISPLAY_STATUS.in_(flt.statuses))

        base = (
            select(C, DISPLAY_STATUS.label("display_status"), _users.c.full_name, _okrugs.c.short, _districts.c.name)
            .outerjoin(_users, _users.c.id == C.author_id)
            .outerjoin(_okrugs, _okrugs.c.code == C.okrug_code)
            .outerjoin(_districts, _districts.c.code == C.district_code)
            .where(*conditions)
        )
        # подсчёт — без вычисляемого статуса и справочных join (6.1): они нужны только строкам страницы
        counted = select(C.id).select_from(C)
        if flt.q:
            counted = counted.outerjoin(_users, _users.c.id == C.author_id)
        total = int(
            (
                await self._s.execute(select(func.count()).select_from(counted.where(*conditions).subquery()))
            ).scalar_one()
        )
        rows = (
            await self._s.execute(
                base.order_by(_REGISTERED_AT.desc(), C.number.desc()).limit(flt.limit).offset(flt.offset)
            )
        ).all()
        return [self._row(*r) for r in rows], total

    @staticmethod
    def _row(c: C, display: str, author: str | None, okrug: str | None, district: str | None) -> JournalRow:
        flags: dict[str, Any] = (c.payload or {}).get("flags") or {}
        empty = "no_contact" if flags.get("no_contact") else "call_dropped" if flags.get("call_dropped") else None
        return JournalRow(
            id=c.id,
            number=c.number,
            display_status=display,
            checked=c.status == "checked",
            is_emergency=c.is_emergency,
            is_incident=c.is_incident,
            operator_number=c.operator_number,
            arm_number=c.arm_number,
            author_name=author,
            channel=c.channel,
            registered_at=as_utc(c.opened_at) or as_utc(c.created_at),
            card_types=list(c.card_type_codes or []),
            empty_call=empty,
            has_victims=c.has_victims,
            victims_count=c.victims_count,
            address_line=_address(c.address_text, okrug, district),
            description=c.description,
        )

    # ------------------------------------------------------------------ карточка

    async def get(self, card_id: UUID) -> CardView | None:
        checker = _users.alias("checker")
        found = (
            await self._s.execute(
                select(C, DISPLAY_STATUS, _users.c.full_name, checker.c.full_name, _okrugs.c.short, _districts.c.name)
                .outerjoin(_users, _users.c.id == C.author_id)
                .outerjoin(checker, checker.c.id == C.checked_by)
                .outerjoin(_okrugs, _okrugs.c.code == C.okrug_code)
                .outerjoin(_districts, _districts.c.code == C.district_code)
                .where(C.id == card_id)
            )
        ).first()
        if found is None:
            return None
        card, display, author_name, checker_name, okrug, district = found

        history: dict[str, list[StatusHistoryItem]] = {}
        for code, status, at, comment, op, order_no in (
            await self._s.execute(
                select(
                    CardServiceStatusModel.service_code,
                    CardServiceStatusModel.status,
                    CardServiceStatusModel.at,
                    CardServiceStatusModel.comment,
                    _users.c.operator_number,
                    CardServiceStatusModel.order_no,
                )
                .outerjoin(_users, _users.c.id == CardServiceStatusModel.actor_id)
                .where(CardServiceStatusModel.card_id == card_id)
                .order_by(CardServiceStatusModel.id)
            )
        ).all():
            history.setdefault(code, []).append(
                StatusHistoryItem(status=status, at=as_utc(at), operator=op, comment=comment, order_no=order_no)
            )

        services: list[CardServiceView] = []
        for svc, short, integrated in (
            await self._s.execute(
                select(CS, _services.c.short_name, _services.c.integrated)
                .outerjoin(_services, _services.c.code == CS.service_code)
                .where(CS.card_id == card_id)
            )
        ).all():
            items = history.get(svc.service_code, [])
            services.append(
                CardServiceView(
                    code=svc.service_code,
                    short=short or svc.service_code,
                    integrated=True if integrated is None else bool(integrated),  # SQLite отдаёт 0/1
                    is_main=svc.is_main,
                    added_by=svc.added_by,
                    status=svc.current_status,
                    status_at=items[-1].at if items else None,
                    history=items,
                )
            )
        workouts = [
            WorkoutView(
                id=w.id,
                at=as_utc(w.at) or w.at,
                operator_number=w.operator_number,
                service_code=w.service_code,
                target=w.target,
                called_to=w.called_to,
                phone=w.phone,
                receiver=w.receiver,
                message=w.message,
            )
            for w in (await self._s.execute(select(W).where(W.card_id == card_id).order_by(W.at))).scalars()
        ]
        type_codes = list(card.incident_type_codes or [])
        types: dict[str, IncidentTypeInfo] = {}
        if type_codes:
            stmt = select(_types.c.code, _types.c.final_type, _types.c.ekp_type).where(_types.c.code.in_(type_codes))
            for code, final, ekp in (await self._s.execute(stmt)).all():
                types[code] = IncidentTypeInfo(code=code, final_type=final, ekp_type=ekp)
        rework = None
        if card.status == "registered":
            last = (
                await self._s.execute(
                    select(_audit.c.event, _audit.c.description, _audit.c.at, _audit.c.actor_name)
                    .where(_audit.c.card_number == card.number, _audit.c.event.in_(("card.returned", "card.worked")))
                    .order_by(_audit.c.id.desc())
                    .limit(1)
                )
            ).first()
            if last is not None and last[0] == "card.returned":
                rework = ReworkNote(comment=last[1] or "", at=as_utc(last[2]), by=last[3])
        return CardView(
            rework=rework,
            id=card.id,
            number=card.number,
            status=card.status,
            display_status=display,
            author_id=card.author_id,
            author_name=author_name,
            operator_number=card.operator_number,
            arm_number=card.arm_number,
            opened_at=as_utc(card.opened_at),
            saved_at=as_utc(card.saved_at),
            worked_at=as_utc(card.worked_at),
            checked_at=as_utc(card.checked_at),
            checked_by_name=checker_name,
            processing_ms=card.processing_ms,
            is_emergency=card.is_emergency,
            is_incident=card.is_incident,
            address_line=_address(card.address_text, okrug, district),
            data=dict(card.payload or {}),
            services=services,
            workouts=workouts,
            incident_types=[types[c] for c in type_codes if c in types],
        )
