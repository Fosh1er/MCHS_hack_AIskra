"""SQL-хранилище training: сценарии и учебные звонки."""

from __future__ import annotations

import random
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from aiskra.modules.training.application.ports.scenarios import ScenarioRow
from aiskra.modules.training.domain.call import Call, CallMessage, CallParty, CallStatus, ReplicaVia, Speaker
from aiskra.modules.training.domain.scenario import Scenario, ScenarioStatus
from aiskra.modules.training.domain.tone import CallerTone, ToneSnapshot
from aiskra.modules.training.infrastructure.models import CallMessageModel, CallModel, ScenarioModel
from aiskra.platform.types import as_utc


def _group(code: str | None) -> int | None:
    """Группа классификатора из кода типа: 1010101 → 1, 22020000 → 22."""
    return int(code[:-6]) if code and len(code) > 6 and code[:-6].isdigit() else None


class SqlScenarioRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, scenario: Scenario) -> None:
        row = ScenarioModel(id=scenario.id)
        self._fill(row, scenario)
        self._s.add(row)
        await self._s.flush()

    async def save(self, scenario: Scenario) -> None:
        row = await self._s.get(ScenarioModel, scenario.id)
        if row is None:
            raise LookupError(f"Сценарий {scenario.id} не найден")
        self._fill(row, scenario)
        await self._s.flush()

    @staticmethod
    def _fill(row: ScenarioModel, scenario: Scenario) -> None:
        row.title = scenario.title
        row.status = scenario.status.value
        row.difficulty = scenario.difficulty
        row.roles = list(scenario.roles)
        row.card_type_code = scenario.card_type_code
        row.incident_type_code = scenario.incident_type_code
        row.legend = scenario.legend
        row.reference_card = scenario.reference_card
        row.reference_dds = scenario.reference_dds
        row.source = scenario.source
        row.author_id = scenario.author_id
        row.approved_by = scenario.approved_by
        if scenario.status is ScenarioStatus.APPROVED and row.approved_at is None:
            row.approved_at = func.now()

    async def get(self, scenario_id: UUID) -> Scenario | None:
        row = await self._s.get(ScenarioModel, scenario_id)
        if row is None:
            return None
        return Scenario(
            id=row.id,
            title=row.title,
            difficulty=row.difficulty,
            card_type_code=row.card_type_code or "",
            incident_type_code=row.incident_type_code or "",
            legend=dict(row.legend or {}),
            reference_card=dict(row.reference_card or {}),
            reference_dds=dict(row.reference_dds or {}),
            roles=list(row.roles or []),
            source=row.source,
            status=ScenarioStatus(row.status),
            author_id=row.author_id,
            approved_by=row.approved_by,
        )

    async def page(
        self,
        *,
        status: str | None,
        difficulty: int | None,
        card_type: str | None,
        source: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[ScenarioRow], int]:
        stmt = select(ScenarioModel)
        stmt = stmt.where(ScenarioModel.status == status if status else ScenarioModel.status != "archived")
        if difficulty:
            stmt = stmt.where(ScenarioModel.difficulty == difficulty)
        if card_type:
            stmt = stmt.where(ScenarioModel.card_type_code == card_type)
        if source:
            stmt = stmt.where(ScenarioModel.source == source)
        total = int((await self._s.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one())
        rows = (
            await self._s.execute(stmt.order_by(ScenarioModel.created_at.desc()).limit(limit).offset(offset))
        ).scalars()
        return [
            ScenarioRow(
                id=r.id,
                title=r.title,
                status=r.status,
                difficulty=r.difficulty,
                card_type_code=r.card_type_code,
                incident_type_code=r.incident_type_code,
                source=r.source,
                created_at=as_utc(r.created_at),
            )
            for r in rows
        ], total

    async def random_approved(
        self, rng: random.Random, groups: list[int] | None, difficulty: int | None = None
    ) -> Scenario | None:
        found = (
            await self._s.execute(
                select(ScenarioModel.id, ScenarioModel.incident_type_code, ScenarioModel.difficulty).where(
                    ScenarioModel.status == "approved"
                )
            )
        ).all()
        pool = [(sid, diff) for sid, code, diff in found if not groups or _group(code) in groups]
        if pool and difficulty is not None:  # сложность занятия (п. 3.7): сначала сценарии нужного уровня
            best = min(abs(d - difficulty) for _, d in pool)
            pool = [(sid, d) for sid, d in pool if abs(d - difficulty) == best]
        return await self.get(rng.choice(pool)[0]) if pool else None


class SqlCallRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, call: Call) -> None:
        self._s.add(
            CallModel(
                id=call.id,
                student_id=call.student_id,
                role=call.role,
                party=call.party.value,
                direction=call.direction,
                started_at=call.started_at,
                aon=call.aon,
                revealed=[],
            )
        )
        await self._s.flush()
        await self.save(call)

    async def save(self, call: Call) -> None:
        row = await self._s.get(CallModel, call.id)
        if row is None:
            raise LookupError(f"Звонок {call.id} не найден")
        row.scenario_id = call.scenario_id
        row.card_id = call.card_id
        row.service_code = call.service_code
        row.target_service = call.target_service
        row.aon = call.aon
        row.status = call.status.value
        row.revealed = list(call.revealed)
        row.tone = call.tone.to_json() if call.tone else None
        row.answered_at = call.answered_at
        row.ended_at = call.ended_at

    @staticmethod
    def _entity(row: CallModel) -> Call:
        started = as_utc(row.started_at)
        assert started is not None
        return Call(
            id=row.id,
            student_id=row.student_id,
            role=row.role,
            party=CallParty(row.party),
            direction=row.direction,
            started_at=started,
            scenario_id=row.scenario_id,
            card_id=row.card_id,
            service_code=row.service_code,
            target_service=row.target_service,
            aon=row.aon,
            status=CallStatus(row.status),
            answered_at=as_utc(row.answered_at),
            ended_at=as_utc(row.ended_at),
            revealed=list(row.revealed or []),
            tone=CallerTone.from_json(row.tone),
        )

    async def get(self, call_id: UUID) -> Call | None:
        row = await self._s.get(CallModel, call_id)
        return self._entity(row) if row else None

    async def add_message(self, message: CallMessage) -> None:
        self._s.add(
            CallMessageModel(
                id=message.id,
                call_id=message.call_id,
                speaker=message.speaker.value,
                text=message.text,
                at=message.at,
                tone=message.tone.to_json() if message.tone else None,
                via=message.via.value if message.via else None,
            )
        )
        await self._s.flush()

    async def messages(self, call_id: UUID) -> list[CallMessage]:
        rows = (
            await self._s.execute(
                select(CallMessageModel)
                .where(CallMessageModel.call_id == call_id)
                .order_by(CallMessageModel.at, CallMessageModel.id)
            )
        ).scalars()
        out = []
        for r in rows:
            at = as_utc(r.at)
            assert at is not None
            out.append(
                CallMessage(
                    id=r.id,
                    call_id=r.call_id,
                    speaker=Speaker(r.speaker),
                    text=r.text,
                    at=at,
                    tone=ToneSnapshot.from_json(r.tone),
                    via=ReplicaVia(r.via) if r.via else None,
                )
            )
        return out

    async def calls_of_card(self, card_id: UUID, student_id: UUID | None) -> list[Call]:
        stmt = select(CallModel).where(CallModel.card_id == card_id)
        if student_id is not None:
            stmt = stmt.where(or_(CallModel.student_id == student_id))
        rows = (await self._s.execute(stmt.order_by(CallModel.started_at))).scalars()
        return [self._entity(r) for r in rows]
