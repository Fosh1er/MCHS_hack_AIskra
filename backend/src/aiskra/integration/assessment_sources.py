"""Порт `AttemptSource` модуля assessment поверх incidents (карточка, статусы служб) и training (сценарий, звонки)."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aiskra.modules.assessment.application.ports.attempts import Card112Attempt, DdsAttempt
from aiskra.modules.assessment.domain.psy_scoring import PsyAttempt, PsyTurn
from aiskra.modules.assessment.domain.scoring import CallerFacts, StatusStep
from aiskra.modules.dictionaries.infrastructure.models import EnumValueModel, ServiceModel
from aiskra.modules.incidents.infrastructure.models import CardServiceModel, CardServiceStatusModel, IncidentCardModel
from aiskra.modules.incidents.infrastructure.reader import SqlCardReader
from aiskra.modules.training.domain.actors import topic_of
from aiskra.modules.training.domain.tone import ToneSnapshot
from aiskra.modules.training.infrastructure.models import CallMessageModel, CallModel, ScenarioModel
from aiskra.platform.types import as_utc


class IncidentAttempts:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def _psy(self, card_id: UUID, role: str, service_code: str | None, services: list[str]) -> PsyAttempt | None:
        """Последний разговор с заявителем, у которого был психологический профиль (п. 3.7)."""
        stmt = select(CallModel).where(
            CallModel.card_id == card_id, CallModel.role == role, CallModel.party == "applicant"
        )
        if service_code:
            stmt = stmt.where(CallModel.service_code == service_code)
        calls = [c for c in (await self._s.execute(stmt.order_by(CallModel.started_at))).scalars() if c.psy]
        if not calls:
            return None
        call = calls[-1]
        rows = (
            await self._s.execute(
                select(CallMessageModel)
                .where(CallMessageModel.call_id == call.id)
                .order_by(CallMessageModel.at, CallMessageModel.id)
            )
        ).scalars()
        begin = as_utc(call.answered_at) or as_utc(call.started_at)
        turns = []
        for r in rows:
            meta = dict(r.meta or {})
            at = as_utc(r.at)
            signals = meta.get("signals") or {}
            acts = meta.get("acts") or []
            turns.append(
                PsyTurn(
                    speaker=r.speaker,
                    text=r.text,
                    at_s=(at - begin).total_seconds() if at and begin else 0.0,
                    acts=tuple(a["code"] for a in acts),
                    quotes={a["code"]: a.get("quote", "") for a in acts},
                    level_before=meta.get("level_before"),
                    level_after=meta.get("level_after"),
                    level=meta.get("level"),
                    emotional=bool(meta.get("emotional")),
                    remarks=tuple(meta.get("remarks") or ()),
                    topic=meta.get("topic") if r.speaker == "operator" else None,
                    blocked=meta.get("blocked"),
                    has_signals=bool(signals.get("latency_ms") is not None or signals.get("interrupted")),
                )
            )
        # тема ответа заявителя = тема вопроса оператора перед ним
        fixed: list[PsyTurn] = []
        last_topic: str | None = None
        for t in turns:
            if t.speaker == "operator":
                last_topic = t.topic
                fixed.append(t)
            else:
                fixed.append(replace(t, topic=last_topic if t.speaker == "party" else None))
        return PsyAttempt(
            profile=dict(call.psy or {}), turns=fixed, ended_by=call.ended_by, services=services, call_id=str(call.id)
        )

    async def _scenario(self, card_id: UUID) -> ScenarioModel | None:
        sid = (
            await self._s.execute(select(IncidentCardModel.scenario_id).where(IncidentCardModel.id == card_id))
        ).scalar_one_or_none()
        return await self._s.get(ScenarioModel, sid) if sid else None

    async def _caller(self, calls: list[UUID]) -> CallerFacts | None:
        """Состояние ИИ-заявителя по снимкам у его реплик (п. 3.6): первая и последняя реплика, причины изменений."""
        rows: list[Any] = list(
            (
                await self._s.execute(
                    select(CallMessageModel.tone)
                    .where(CallMessageModel.call_id.in_(calls), CallMessageModel.speaker == "party")
                    .order_by(CallMessageModel.at)
                )
            )
            .scalars()
            .all()
        )
        snaps = [s for s in (ToneSnapshot.from_json(r) for r in rows) if s is not None]
        if not snaps:
            return None
        changes = [c for s in snaps for c in s.changes]
        return CallerFacts(
            start=snaps[0].tension,
            end=snaps[-1].tension,
            calming=sum(1 for c in changes if c.reason == "calming"),
            invalidating=[c.fragment for c in changes if c.reason == "invalidating"],
            pressure=[c.fragment for c in changes if c.reason == "pressure"],
            start_emotion=snaps[0].emotion_title,
            end_emotion=snaps[-1].emotion_title,
        )

    async def card_112(self, card_id: UUID) -> Card112Attempt | None:
        card = await SqlCardReader(self._s).get(card_id)
        if card is None:
            return None
        scenario = await self._scenario(card_id)
        calls = (
            (await self._s.execute(select(CallModel.id).where(CallModel.card_id == card_id, CallModel.role == "112")))
            .scalars()
            .all()
        )
        topics: set[str] | None = None
        if calls:
            texts = (
                (
                    await self._s.execute(
                        select(CallMessageModel.text).where(
                            CallMessageModel.call_id.in_(calls), CallMessageModel.speaker == "operator"
                        )
                    )
                )
                .scalars()
                .all()
            )
            topics = {t for t in (topic_of(x) for x in texts) if t}
        reference = dict(scenario.reference_card) if scenario and scenario.reference_card else None
        codes = {s.code for s in card.services} | {s["code"] for s in (reference or {}).get("services", [])}
        names = dict(
            (
                await self._s.execute(
                    select(ServiceModel.code, ServiceModel.short_name).where(ServiceModel.code.in_(codes))
                )
            ).all()
        )
        flags = dict(
            (
                await self._s.execute(
                    select(EnumValueModel.code, EnumValueModel.name).where(EnumValueModel.domain == "card_flag")
                )
            ).all()
        )
        legend = dict(scenario.legend or {}) if scenario else {}
        public = {k: legend[k] for k in ("what", "details", "address", "victims", "facts") if k in legend}
        services = [s.code for s in card.services]
        psy = await self._psy(card.id, "112", None, services)
        status = (psy.profile.get("applicant_status") if psy else None) or None
        if reference is not None and status:  # профиль меняет статус заявителя (очевидец при ступоре)
            reference = {**reference, "applicant": {**(reference.get("applicant") or {}), "status": status}}
        return Card112Attempt(
            card_id=card.id,
            card_number=card.number,
            author_id=card.author_id,
            status=card.status,
            data=card.data,
            services=[s.code for s in card.services],
            processing_s=card.processing_ms / 1000 if card.processing_ms is not None else None,
            reference=reference,
            legend_text=json.dumps(public, ensure_ascii=False),
            asked_topics=topics,
            service_names=names,
            flag_names={k: v.lower() for k, v in flags.items()},
            caller=await self._caller(list(calls)) if calls else None,
            psy=psy,
        )

    async def dds(self, card_id: UUID, service_code: str) -> DdsAttempt | None:
        card = await SqlCardReader(self._s).get(card_id)
        own = next((s for s in card.services if s.code == service_code), None) if card else None
        if card is None or own is None:
            return None
        rows = (
            (
                await self._s.execute(
                    select(CardServiceStatusModel)
                    .where(
                        CardServiceStatusModel.card_id == card_id, CardServiceStatusModel.service_code == service_code
                    )
                    .order_by(CardServiceStatusModel.id)
                )
            )
            .scalars()
            .all()
        )
        history = [StatusStep(status=r.status, at=as_utc(r.at), order_no=r.order_no, comment=r.comment) for r in rows]
        actors = {r.actor_id for r in rows if r.actor_id and r.status not in ("added",)}
        added = next((h.at for h in history if h.status == "added"), None) or as_utc(card.saved_at)
        paused_ms = (
            await self._s.execute(
                select(CardServiceModel.paused_ms).where(
                    CardServiceModel.card_id == card_id, CardServiceModel.service_code == service_code
                )
            )
        ).scalar_one_or_none()
        if added is not None and paused_ms:  # п. 5.3: пауза на подсказки не входит во время реакции
            added += timedelta(milliseconds=paused_ms)
        parties = (
            (
                await self._s.execute(
                    select(CallModel.party).where(CallModel.card_id == card_id, CallModel.service_code == service_code)
                )
            )
            .scalars()
            .all()
        )
        scenario = await self._scenario(card_id)
        return DdsAttempt(
            card_id=card.id,
            card_number=card.number,
            service_code=service_code,
            history=history,
            added_at=added,
            reference=dict(scenario.reference_dds) if scenario and scenario.reference_dds else None,
            calls=list(parties),
            actor_ids=actors,
            psy=await self._psy(card.id, "dds", service_code, [s.code for s in card.services]),
        )
