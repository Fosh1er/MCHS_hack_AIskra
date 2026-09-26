"""Порты занятий поверх incidents, training и assessment: системные карточки в очередь ДДС, мониторинг прогресса
(training) и факты занятия для отчёта (assessment)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aiskra.modules.assessment.application.ports.reports import ReportCard, ReportParticipant, SessionFacts
from aiskra.modules.assessment.infrastructure.models import AssessmentModel
from aiskra.modules.incidents.domain.card import IncidentCardData
from aiskra.modules.incidents.domain.incident import AddedBy, CardService, IncidentCard
from aiskra.modules.incidents.infrastructure.models import CardServiceModel, IncidentCardModel
from aiskra.modules.incidents.infrastructure.repositories import SqlCardRepository
from aiskra.modules.training.application.ports.sessions import ParticipantProgress
from aiskra.modules.training.domain.scenario import Scenario
from aiskra.modules.training.domain.session import TrainingSession
from aiskra.modules.training.infrastructure.sessions import SqlSessionRepository, SqlStudentDirectory
from aiskra.platform.types import as_utc

WAITING = ("added", "received")
FINAL = ("works_completed", "rejected", "works_refused")


def card_data_from_scenario(s: Scenario) -> dict[str, Any]:
    """Данные карточки 112 так, как их занёс бы безошибочный оператор: эталон сценария + описание из легенды."""
    ref, legend = s.reference_card, s.legend
    a = ref.get("address") or {}
    return {
        "phones": {"aon": (ref.get("phones") or {}).get("aon", ""), "provided": "", "on_site": "", "foreign": False},
        "channel": "mts",
        "applicant": {**(ref.get("applicant") or {}), "foreign_language": False},
        "victims": ref.get("victims") or {"has": False, "count": 0},
        "card_types": ref.get("card_types") or [],
        "incident_types": ref.get("incident_types") or [],
        "questionnaire": ref.get("questionnaire") or {},
        "card_flags": ref.get("card_flags") or [],
        "address": {
            "street": a.get("street") or "",
            "house": a.get("house") or "",
            "building": a.get("building") or "",
            "structure": a.get("structure") or "",
            "okrug": a.get("okrug"),
            "district": a.get("district"),
            "floor": a.get("floor") or "",
            "flat": a.get("flat") or "",
            "lat": a.get("lat"),
            "lon": a.get("lon"),
        },
        "description": str(legend.get("what") or ref.get("final_type") or "")[:1999],
    }


class IncidentSystemCards:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create_from_scenario(
        self, scenario: Scenario, *, extra_service: str | None, session_id: UUID, author_id: UUID
    ) -> UUID:
        repo = SqlCardRepository(self._s)
        now = datetime.now(UTC)
        card = IncidentCard(
            author_id=author_id,
            opened_at=now,
            operator_number="0",
            arm_number="112",
            scenario_id=scenario.id,
            session_id=session_id,
            origin="system",
        )
        await repo.add(card)
        services = [
            CardService(code=x["code"], is_main=bool(x.get("main")), added_by=AddedBy.AUTO)
            for x in scenario.reference_card.get("services", [])
        ]
        if extra_service and extra_service not in {x.code for x in services}:
            services.append(CardService(code=extra_service, is_main=False, added_by=AddedBy.MANUAL))
        card.save(IncidentCardData.from_dict(card_data_from_scenario(scenario)), services, now)
        await repo.register(card)
        return card.id

    async def waiting(self, service_code: str, session_id: UUID) -> tuple[int, datetime | None]:
        base = (
            select(CardServiceModel.current_status, IncidentCardModel.saved_at)
            .join(IncidentCardModel, IncidentCardModel.id == CardServiceModel.card_id)
            .where(CardServiceModel.service_code == service_code, IncidentCardModel.session_id == session_id)
        )
        rows = (await self._s.execute(base)).all()
        waiting = sum(1 for st, _ in rows if st in WAITING)
        last = max((at for _, at in rows if at), default=None)
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        return waiting, last


class SessionProgress:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def _assessments(self, card_ids: list[UUID], role: str, service: str | None) -> list[dict[str, Any]]:
        if not card_ids:
            return []
        rows = (
            await self._s.execute(
                select(AssessmentModel)
                .where(AssessmentModel.card_id.in_(card_ids))
                .order_by(AssessmentModel.created_at.desc())
            )
        ).scalars()
        latest: dict[UUID, dict[str, Any]] = {}
        for r in rows:
            d = r.details or {}
            if (
                d.get("role") == role
                and (role != "dds" or d.get("service_code") == service)
                and r.card_id is not None
                and r.card_id not in latest
            ):
                latest[r.card_id] = {"score": r.score, "errors": d.get("errors", [])}
        return list(latest.values())

    async def progress(self, session: TrainingSession) -> list[ParticipantProgress]:
        cards = (
            (
                await self._s.execute(
                    select(IncidentCardModel)
                    .where(IncidentCardModel.session_id == session.id)
                    .order_by(IncidentCardModel.opened_at)
                )
            )
            .scalars()
            .all()
        )
        out = []
        for p in session.participants:
            if p.role == "112":
                mine = [c for c in cards if c.author_id == p.student_id]
                done = [c for c in mine if c.status != "draft"]
                draft = next((c for c in reversed(mine) if c.status == "draft"), None)
                waiting: list[IncidentCardModel] = []
                marks = await self._assessments([c.id for c in done], "112", None)
                current = draft or (done[-1] if done else None)
                since = draft.opened_at if draft else None
            else:
                svc = p.dds_service_code or ""
                statuses = (
                    dict(
                        (
                            await self._s.execute(
                                select(CardServiceModel.card_id, CardServiceModel.current_status).where(
                                    CardServiceModel.service_code == svc,
                                    CardServiceModel.card_id.in_([c.id for c in cards]),
                                )
                            )
                        ).all()
                    )
                    if cards
                    else {}
                )
                mine = [c for c in cards if c.id in statuses]
                done = [c for c in mine if statuses[c.id] in FINAL]
                waiting = [c for c in mine if statuses[c.id] in WAITING]
                marks = await self._assessments([c.id for c in mine], "dds", svc)
                current = waiting[0] if waiting else None
                since = current.saved_at if current else None
            if since is not None and since.tzinfo is None:
                since = since.replace(tzinfo=UTC)
            scores = [m["score"] for m in marks if m["score"] is not None]
            errors = [e for m in marks for e in m["errors"]]
            out.append(
                ParticipantProgress(
                    student_id=p.student_id,
                    cards_done=len(done),
                    current_card=current.number if current else None,
                    current_label=", ".join(current.card_type_codes or []) if current else "",
                    current_since=since,
                    waiting=len(waiting) if p.role == "dds" else 0,
                    avg_score=round(sum(scores) / len(scores), 1) if scores else None,
                    errors=len(errors),
                    last_errors=errors[-3:],
                )
            )
        return out


async def count_session_cards(session: AsyncSession, session_id: UUID) -> int:
    return int(
        (await session.execute(select(func.count()).where(IncidentCardModel.session_id == session_id))).scalar_one()
    )


class SessionFactsReader:
    """`SessionFactsSource` для отчёта: занятие, участники с ФИО и все карточки занятия со статусами служб."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def session(self, session_id: UUID) -> SessionFacts | None:
        ts = await SqlSessionRepository(self._s).get(session_id)
        if ts is None:
            return None
        names = await SqlStudentDirectory(self._s).names([p.student_id for p in ts.participants])
        cards = (
            (
                await self._s.execute(
                    select(IncidentCardModel)
                    .where(IncidentCardModel.session_id == session_id)
                    .order_by(IncidentCardModel.opened_at)
                )
            )
            .scalars()
            .all()
        )
        services: dict[UUID, dict[str, str]] = {}
        if cards:
            rows = await self._s.execute(
                select(CardServiceModel.card_id, CardServiceModel.service_code, CardServiceModel.current_status).where(
                    CardServiceModel.card_id.in_([c.id for c in cards])
                )
            )
            for cid, code, st in rows.all():
                services.setdefault(cid, {})[code] = st
        return SessionFacts(
            session_id=ts.id,
            teacher_id=ts.teacher_id,
            title=ts.title,
            mode=ts.mode.value,
            status=ts.status.value,
            started_at=ts.started_at,
            finished_at=ts.finished_at,
            settings=dict(ts.settings),
            participants=[
                ReportParticipant(
                    student_id=p.student_id,
                    full_name=names[p.student_id].full_name if p.student_id in names else str(p.student_id),
                    role=p.role,
                    service_code=p.dds_service_code,
                )
                for p in ts.participants
            ],
            cards=[
                ReportCard(
                    card_id=c.id,
                    number=c.number,
                    author_id=c.author_id,
                    origin=c.origin,
                    status=c.status,
                    saved_at=as_utc(c.saved_at) if c.saved_at else None,
                    processing_s=c.processing_ms / 1000 if c.processing_ms is not None else None,
                    card_types=list(c.card_type_codes or []),
                    services=services.get(c.id, {}),
                )
                for c in cards
            ],
        )
