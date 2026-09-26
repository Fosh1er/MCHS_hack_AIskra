"""Учебные звонки (п. 1.4, 2.3).

112: система «звонит» обучающемуся — случайный утверждённый сценарий (или новый, если банк пуст); «Принять» →
первая реплика заявителя; оператор задаёт вопросы — отвечает ИИ-заявитель по легенде (3.3).
ДДС: звонок из карточки старшему группы своей службы, заявителю (номер из карточки, #739) или в смежную службу."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from uuid import UUID

from aiskra.modules.training.application.actors import Actors
from aiskra.modules.training.application.commands.scenarios import ScenarioGenerator
from aiskra.modules.training.application.ports.scenarios import (
    CallRepository,
    CardContextSource,
    DdsCallContext,
    ScenarioRepository,
)
from aiskra.modules.training.domain.call import Call, CallMessage, CallParty, Speaker
from aiskra.shared.application import Clock, Command, UnitOfWork
from aiskra.shared.audit import AuditEntry, AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.errors import DomainError, NotFoundError
from aiskra.shared.security import Principal

TEXT_MAX = 500
PARTY_GREETING = {
    CallParty.BRIGADE: "Старший группы, слушаю.",
    CallParty.APPLICANT: "Алло?",
}


@dataclass(frozen=True)
class CallStarted:
    call_id: UUID
    scenario_id: UUID | None
    aon: str
    channel: str


@dataclass(frozen=True)
class Replica:
    speaker: str
    text: str


class _CallBase:
    def __init__(
        self,
        calls: CallRepository,
        scenarios: ScenarioRepository,
        cards: CardContextSource,
        actors: Actors,
        uow: UnitOfWork,
        clock: Clock,
    ) -> None:
        self._calls = calls
        self._scenarios = scenarios
        self._cards = cards
        self._actors = actors
        self._uow = uow
        self._clock = clock

    async def _own_call(self, call_id: UUID, actor: Principal) -> Call:
        call = await self._calls.get(call_id)
        if call is None or call.student_id != actor.user_id:
            raise NotFoundError("Звонок не найден", code="call_not_found")
        return call

    async def _commit(self) -> None:
        try:
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise

    async def _say(self, call: Call, speaker: Speaker, text: str) -> CallMessage:
        msg = CallMessage(call_id=call.id, speaker=speaker, text=text, at=self._clock.now())
        await self._calls.add_message(msg)
        return msg


@dataclass(frozen=True, kw_only=True)
class StartIncomingCall(Command):
    actor: Principal
    groups: list[int] = field(default_factory=list)
    difficulty: int = 2
    seed: int | None = None


class StartIncomingCallHandler(_CallBase):
    def __init__(self, *args: object, generator: ScenarioGenerator, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._gen = generator

    async def __call__(self, cmd: StartIncomingCall) -> CallStarted:
        rng = random.Random(cmd.seed)
        scenario = await self._scenarios.random_approved(rng, cmd.groups or None)
        if scenario is None:  # банк пуст — сценарий на лету, сохраняется черновиком для проверки преподавателем
            scenario = await self._gen.generate(rng, cmd.groups, cmd.difficulty, None)
            await self._scenarios.add(scenario)
        aon = scenario.legend.get("applicant", {}).get("phone", "")
        call = Call(
            student_id=cmd.actor.user_id,
            role="112",
            party=CallParty.APPLICANT,
            direction="in",
            started_at=self._clock.now(),
            scenario_id=scenario.id,
            aon=aon,
        )
        await self._calls.add(call)
        await self._commit()
        return CallStarted(call_id=call.id, scenario_id=scenario.id, aon=aon, channel="mts")


@dataclass(frozen=True, kw_only=True)
class AnswerCall(Command):
    actor: Principal
    call_id: UUID
    card_id: UUID | None = None  # карточка, открытая по «Принять»


class AnswerCallHandler(_CallBase):
    async def __call__(self, cmd: AnswerCall) -> Replica | None:
        call = await self._own_call(cmd.call_id, cmd.actor)
        first = call.answered_at is None
        call.answer(self._clock.now())
        if cmd.card_id is not None:
            call.card_id = cmd.card_id
        opening: Replica | None = None
        if first and call.party is CallParty.APPLICANT and call.scenario_id:
            scenario = await self._scenarios.get(call.scenario_id)
            if scenario is not None:
                text = scenario.legend.get("opening") or f"Здравствуйте, у нас {scenario.legend.get('what', 'беда')}."
                call.revealed = [*call.revealed, "opening"]
                await self._say(call, Speaker.PARTY, text)
                opening = Replica(speaker=Speaker.PARTY.value, text=text)
        await self._calls.save(call)
        await self._commit()
        return opening


@dataclass(frozen=True, kw_only=True)
class StartDdsCall(Command):
    actor: Principal
    card_id: UUID
    service_code: str  # своя ДДС
    party: CallParty
    target_service: str | None = None
    incoming: bool = False  # старший группы сам звонит в ДДС с докладом (#691)


class StartDdsCallHandler(_CallBase):
    async def __call__(self, cmd: StartDdsCall) -> CallStarted:
        ctx = await self._cards.dds_context(cmd.card_id, cmd.service_code)
        if ctx is None:
            raise NotFoundError("Карточка не поступала в эту службу", code="dds_card_not_found")
        if cmd.party is CallParty.SERVICE and (not cmd.target_service or cmd.target_service not in ctx.services):
            raise DomainError("Можно звонить только в службы этой карточки", code="bad_target_service")
        call = Call(
            student_id=cmd.actor.user_id,
            role="dds",
            party=cmd.party,
            direction="in" if cmd.incoming else "out",
            started_at=self._clock.now(),
            scenario_id=ctx.scenario_id,
            card_id=cmd.card_id,
            service_code=cmd.service_code,
            target_service=cmd.target_service if cmd.party is CallParty.SERVICE else None,
            aon=ctx.applicant_phone if cmd.party is CallParty.APPLICANT else "",
        )
        call.answer(self._clock.now())  # абонент снимает трубку сразу
        await self._calls.add(call)
        if cmd.incoming and cmd.party is CallParty.BRIGADE:
            short = ctx.services.get(cmd.service_code, (cmd.service_code, ""))[0]
            report = await self._actors.brigade(ctx, short, [], "Доложите обстановку")
            await self._say(call, Speaker.PARTY, f"ДДС? Старший группы. {report}")
            await self._commit()
            return CallStarted(call_id=call.id, scenario_id=ctx.scenario_id, aon="", channel="ip")
        greeting = PARTY_GREETING.get(cmd.party) or (
            f"Дежурный {ctx.services[cmd.target_service or ''][0]}, слушаю." if cmd.target_service else "Слушаю."
        )
        await self._say(call, Speaker.PARTY, greeting)
        await self._commit()
        return CallStarted(call_id=call.id, scenario_id=ctx.scenario_id, aon=call.aon, channel="ip")


@dataclass(frozen=True, kw_only=True)
class SendReplica(Command):
    actor: Principal
    call_id: UUID
    text: str


class SendReplicaHandler(_CallBase):
    async def __call__(self, cmd: SendReplica) -> Replica:
        text = " ".join(cmd.text.split())
        if not text:
            raise DomainError("Пустая реплика", code="empty_replica")
        if len(text) > TEXT_MAX:
            raise DomainError(f"Реплика длиннее {TEXT_MAX} символов", code="replica_too_long")
        call = await self._own_call(cmd.call_id, cmd.actor)
        call.ensure_active()
        history = await self._calls.messages(call.id)
        await self._say(call, Speaker.OPERATOR, text)
        reply = await self._reply(call, history, text)
        await self._say(call, Speaker.PARTY, reply)
        await self._calls.save(call)
        await self._commit()
        return Replica(speaker=Speaker.PARTY.value, text=reply)

    async def _legend_for_card(self, ctx: DdsCallContext) -> dict[str, object]:
        """Карточка без сценария (заполнена обучающимся) — заявитель знает то, что есть в карточке."""
        return {
            "applicant": {"name": ctx.applicant_name, "phone": ctx.applicant_phone},
            "address": {"label": ctx.address or ""},
            "what": ctx.description or "происшествие",
            "victims": {"has": ctx.victims not in ("нет", "0"), "count": ctx.victims},
            "emotion": "спокойно",
        }

    async def _reply(self, call: Call, history: list[CallMessage], text: str) -> str:
        if call.party is CallParty.APPLICANT:
            legend: dict[str, object] = {}
            if call.scenario_id:
                scenario = await self._scenarios.get(call.scenario_id)
                legend = scenario.legend if scenario else {}
            if not legend and call.card_id and call.service_code:
                ctx = await self._cards.dds_context(call.card_id, call.service_code)
                legend = await self._legend_for_card(ctx) if ctx else {}
            answer, revealed = await self._actors.applicant(
                legend, history, text, call.revealed, str(call.scenario_id or call.card_id)
            )
            call.revealed = revealed
            return answer
        if call.card_id is None or call.service_code is None:
            raise DomainError("Звонок не связан с карточкой", code="call_without_card")
        ctx = await self._cards.dds_context(call.card_id, call.service_code)
        if ctx is None:
            raise NotFoundError("Карточка не найдена", code="dds_card_not_found")
        if call.party is CallParty.BRIGADE:
            return await self._actors.brigade(
                ctx, ctx.services.get(call.service_code, (call.service_code, ""))[0], history, text
            )
        return await self._actors.service(ctx, call.target_service or "", history, text)


@dataclass(frozen=True, kw_only=True)
class EndCall(Command):
    actor: Principal
    call_id: UUID
    meta: RequestMeta = field(default_factory=RequestMeta)


class EndCallHandler(_CallBase):
    def __init__(self, *args: object, audit: AuditRecorder, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._audit = audit

    async def __call__(self, cmd: EndCall) -> str:
        call = await self._own_call(cmd.call_id, cmd.actor)
        was_active = call.ended_at is None
        call.end(self._clock.now())
        await self._calls.save(call)
        if was_active:
            who = {
                CallParty.APPLICANT: "заявитель",
                CallParty.BRIGADE: "старший группы",
                CallParty.SERVICE: "смежная служба",
            }
            secs = int((call.ended_at - call.started_at).total_seconds()) if call.ended_at else 0
            direction = "Входящий" if call.direction == "in" else "Исходящий"
            await self._audit.record(
                AuditEntry(
                    event=AuditEvent.CALL_ENDED,
                    actor=cmd.actor,
                    meta=cmd.meta,
                    description=f"{direction} звонок: {who[call.party]}, {secs} с",
                    object_type="call",
                    object_id=str(call.id),
                    data={"card_id": str(call.card_id) if call.card_id else None, "party": call.party.value},
                )
            )
        await self._commit()
        return call.status.value
