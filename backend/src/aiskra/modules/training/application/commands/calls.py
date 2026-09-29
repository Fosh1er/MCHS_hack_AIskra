"""Учебные звонки (п. 1.4, 2.3).

112: система «звонит» обучающемуся — случайный утверждённый сценарий (или новый, если банк пуст); «Принять» →
первая реплика заявителя; оператор задаёт вопросы — отвечает ИИ-заявитель по легенде (3.3).
ДДС: звонок из карточки старшему группы своей службы, заявителю (номер из карточки, #739) или в смежную службу."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from aiskra.modules.training.application.actors import Actors
from aiskra.modules.training.application.commands.scenarios import ScenarioGenerator
from aiskra.modules.training.application.ports.scenarios import (
    CallRepository,
    CardContextSource,
    DdsCallContext,
    ScenarioRepository,
)
from aiskra.modules.training.application.ports.sessions import ServiceSwitches, SessionRepository
from aiskra.modules.training.application.psy import PsyDirector, TurnSignals, start_psy
from aiskra.modules.training.domain.actors import topic_of
from aiskra.modules.training.domain.call import Call, CallMessage, CallParty, ReplicaVia, Speaker
from aiskra.modules.training.domain.psy import choose_profile, psy_settings
from aiskra.modules.training.domain.scenario import Scenario
from aiskra.modules.training.domain.tone import CallerTone, ToneSnapshot, tone_for_legend
from aiskra.shared.application import Clock, Command, UnitOfWork
from aiskra.shared.audit import AuditEntry, AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.errors import DomainError, NotFoundError
from aiskra.shared.security import Principal

TEXT_MAX = 500
PARTY_GREETING = {
    CallParty.BRIGADE: "Старший группы, слушаю.",
    CallParty.APPLICANT: "Алло?",
}


SENSITIVE_WARNING = (
    "Учебный звонок может затрагивать тяжёлую тему (кризисное состояние заявителя). Вы можете отказаться — "
    "отказ не оценивается. После звонка обязателен разбор с преподавателем."
)


@dataclass(frozen=True)
class CallStarted:
    call_id: UUID
    scenario_id: UUID | None
    aon: str
    channel: str
    warning: str | None = None  # п. 3.7: предупреждение перед профилем `sensitive`


@dataclass(frozen=True)
class Replica:
    speaker: str
    text: str
    message_id: UUID | None = None
    tone: ToneSnapshot | None = None  # состояние заявителя у этой реплики (п. 3.6)
    remarks: list[str] = field(default_factory=list)  # п. 3.7: ремарки заявителя (*плачет*)
    voice: dict[str, object] | None = None  # п. 3.7: параметры голоса профиля для синтеза / дуплекс-адаптера
    hung_up: bool = False  # заявитель положил трубку


class _CallBase:
    def __init__(
        self,
        calls: CallRepository,
        scenarios: ScenarioRepository,
        cards: CardContextSource,
        actors: Actors,
        uow: UnitOfWork,
        clock: Clock,
        *,
        psy: PsyDirector | None = None,
        sessions: SessionRepository | None = None,
    ) -> None:
        self._calls = calls
        self._scenarios = scenarios
        self._cards = cards
        self._actors = actors
        self._uow = uow
        self._clock = clock
        self._psy = psy
        self._sessions = sessions

    async def _assign_psy(self, call: Call, scenario: Scenario | None, rng: random.Random) -> str | None:
        """Психологический профиль заявителя по настройкам идущего занятия (п. 3.7). Возвращает предупреждение."""
        if self._psy is None or self._sessions is None or scenario is None:
            return None
        session = await self._sessions.running_for_student(call.student_id)
        if session is None:
            return None
        settings = psy_settings(session.settings.get("psy"))
        catalog = self._psy.catalog.profiles()
        profile = choose_profile(catalog, settings, scenario.difficulty, rng, pinned=scenario.psy_profile)
        if profile is None:
            return None
        call.psy = start_psy(
            profile,
            seed=rng.randrange(1, 2**31),
            catalog_version=self._psy.catalog.version,
            settings=settings,
            session_id=str(session.id),
        )
        return SENSITIVE_WARNING if profile.sensitive else None

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

    async def _say(
        self,
        call: Call,
        speaker: Speaker,
        text: str,
        tone: ToneSnapshot | None = None,
        via: ReplicaVia | None = None,
        meta: dict[str, Any] | None = None,
    ) -> CallMessage:
        msg = CallMessage(
            call_id=call.id, speaker=speaker, text=text, at=self._clock.now(), tone=tone, via=via, meta=meta
        )
        await self._calls.add_message(msg)
        return msg

    async def _ensure_tone(
        self, call: Call, legend: dict[str, Any] | None = None, incident_code: str | None = None
    ) -> CallerTone | None:
        """Состояние заявителя (п. 3.6). Звонок, начатый до п. 3.6, получает его при первой реплике."""
        if call.party is not CallParty.APPLICANT:
            return None
        if call.tone is None:
            if legend is None and call.scenario_id:
                scenario = await self._scenarios.get(call.scenario_id)
                if scenario is not None:
                    legend, incident_code = scenario.legend, scenario.incident_type_code
            call.tone = tone_for_legend(legend or {}, incident_code)
        return call.tone


@dataclass(frozen=True, kw_only=True)
class StartIncomingCall(Command):
    actor: Principal
    groups: list[int] = field(default_factory=list)
    difficulty: int | None = None  # сложность занятия; вне занятия — любой сценарий банка
    seed: int | None = None


class StartIncomingCallHandler(_CallBase):
    def __init__(
        self, *args: object, generator: ScenarioGenerator, switches: ServiceSwitches | None = None, **kwargs: object
    ) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._gen = generator
        self._switches = switches

    async def __call__(self, cmd: StartIncomingCall) -> CallStarted:
        if self._switches and not await self._switches.enabled("call_stream"):
            raise DomainError("Поток учебных вызовов остановлен администратором", code="service_stopped")
        rng = random.Random(cmd.seed)
        scenario = await self._scenarios.random_approved(rng, cmd.groups or None, cmd.difficulty)
        if scenario is None:  # банк пуст — сценарий на лету, сохраняется черновиком для проверки преподавателем
            scenario = await self._gen.generate(rng, cmd.groups, cmd.difficulty or 2, None)
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
            tone=tone_for_legend(scenario.legend, scenario.incident_type_code),
        )
        warning = await self._assign_psy(call, scenario, rng)
        await self._calls.add(call)
        await self._commit()
        return CallStarted(call_id=call.id, scenario_id=scenario.id, aon=aon, channel="mts", warning=warning)


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
                styled = self._psy.opening(call.psy, scenario.legend) if self._psy and call.psy else None
                if styled is not None:  # п. 3.7: профиль ведёт и реплику, и голосовое состояние
                    text, remarks, meta, psy_tone = styled
                    call.tone = psy_tone
                    psy_snapshot = psy_tone.snapshot()
                    msg = await self._say(call, Speaker.PARTY, text, psy_snapshot, meta=meta)
                    opening = Replica(
                        speaker=Speaker.PARTY.value,
                        text=text,
                        message_id=msg.id,
                        tone=psy_snapshot,
                        remarks=remarks,
                        voice=meta["voice"],
                    )
                else:
                    tone = await self._ensure_tone(call, scenario.legend, scenario.incident_type_code)
                    snapshot = tone.snapshot() if tone else None
                    msg = await self._say(call, Speaker.PARTY, text, snapshot)
                    opening = Replica(speaker=Speaker.PARTY.value, text=text, message_id=msg.id, tone=snapshot)
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
        if cmd.party is CallParty.APPLICANT and ctx.scenario_id:  # п. 3.7: заявитель в стрессе и для ДДС
            await self._assign_psy(call, await self._scenarios.get(ctx.scenario_id), random.Random())
        tone = await self._ensure_tone(call)  # заявитель по сценарию карточки; без сценария — спокоен
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
        await self._say(call, Speaker.PARTY, greeting, tone.snapshot() if tone else None)
        await self._commit()
        return CallStarted(call_id=call.id, scenario_id=ctx.scenario_id, aon=call.aon, channel="ip")


@dataclass(frozen=True, kw_only=True)
class SendReplica(Command):
    actor: Principal
    call_id: UUID
    text: str
    via: ReplicaVia = ReplicaVia.TEXT
    signals: TurnSignals = field(default_factory=TurnSignals)  # п. 3.7: голосовой канал — задержка, перебивание


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
        if call.psy and self._psy and call.party is CallParty.APPLICANT:
            psy_reply = await self._psy_reply(call, history, text, cmd.via, cmd.signals)
            if psy_reply is not None:
                return psy_reply
        await self._say(call, Speaker.OPERATOR, text, via=cmd.via)
        reply, tone = await self._reply(call, history, text)
        msg = await self._say(call, Speaker.PARTY, reply, tone)
        await self._calls.save(call)
        await self._commit()
        return Replica(speaker=Speaker.PARTY.value, text=reply, message_id=msg.id, tone=tone)

    async def _psy_reply(
        self, call: Call, history: list[CallMessage], text: str, via: ReplicaVia, signals: TurnSignals
    ) -> Replica | None:
        """Ход с психологическим профилем (п. 3.7): состояние, ворота, реплика и разметка — в `PsyDirector`;
        голосовое состояние `CallerTone` выводится из профиля, чтобы синтез озвучил то же состояние."""
        assert self._psy is not None and call.psy is not None
        scenario = await self._scenarios.get(call.scenario_id) if call.scenario_id else None
        if scenario is None:
            return None
        now = self._clock.now()
        elapsed = (now - (call.answered_at or call.started_at)).total_seconds()
        turn = await self._psy.turn(
            call.psy, scenario.legend, history, text, call.revealed, elapsed, signals, str(scenario.id)
        )
        if turn is None:
            return None
        await self._say(call, Speaker.OPERATOR, text, via=via, meta=turn.operator_meta)
        msg = await self._say(call, Speaker.PARTY, turn.text, turn.snapshot, meta=turn.party_meta)
        call.revealed = turn.revealed
        call.psy = turn.psy
        call.tone = turn.tone
        if turn.hung_up:
            call.end(self._clock.now(), by="party")
        await self._calls.save(call)
        await self._commit()
        return Replica(
            speaker=Speaker.PARTY.value,
            text=turn.text,
            message_id=msg.id,
            tone=turn.snapshot,
            remarks=turn.remarks,
            voice=turn.voice,
            hung_up=turn.hung_up,
        )

    async def _legend_for_card(self, ctx: DdsCallContext) -> dict[str, Any]:
        """Карточка без сценария (заполнена обучающимся) — заявитель знает то, что есть в карточке."""
        return {
            "applicant": {"name": ctx.applicant_name, "phone": ctx.applicant_phone},
            "address": {"label": ctx.address or ""},
            "what": ctx.description or "происшествие",
            "victims": {"has": ctx.victims not in ("нет", "0"), "count": ctx.victims},
            "emotion": "спокойно",
        }

    async def _reply(self, call: Call, history: list[CallMessage], text: str) -> tuple[str, ToneSnapshot | None]:
        if call.party is CallParty.APPLICANT:
            legend: dict[str, Any] = {}
            incident_code: str | None = None
            if call.scenario_id:
                scenario = await self._scenarios.get(call.scenario_id)
                if scenario is not None:
                    legend, incident_code = scenario.legend, scenario.incident_type_code
            if not legend and call.card_id and call.service_code:
                ctx = await self._cards.dds_context(call.card_id, call.service_code)
                legend = await self._legend_for_card(ctx) if ctx else {}
            # состояние меняется до ответа: на «успокойтесь!» заявитель отвечает уже взвинченным (п. 3.6)
            tone = await self._ensure_tone(call, legend, incident_code)
            assert tone is not None  # у заявителя состояние есть всегда
            changes = tone.react(text, topic=topic_of(text), revealed=call.revealed)
            answer, revealed = await self._actors.applicant(
                legend, history, text, call.revealed, str(call.scenario_id or call.card_id), tone
            )
            call.revealed = revealed
            return answer, tone.snapshot(changes)
        if call.card_id is None or call.service_code is None:
            raise DomainError("Звонок не связан с карточкой", code="call_without_card")
        ctx = await self._cards.dds_context(call.card_id, call.service_code)
        if ctx is None:
            raise NotFoundError("Карточка не найдена", code="dds_card_not_found")
        if call.party is CallParty.BRIGADE:
            short = ctx.services.get(call.service_code, (call.service_code, ""))[0]
            return await self._actors.brigade(ctx, short, history, text), None
        return await self._actors.service(ctx, call.target_service or "", history, text), None


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
                    data={
                        "card_id": str(call.card_id) if call.card_id else None,
                        "party": call.party.value,
                        "psy_profile": (call.psy or {}).get("profile"),
                    },
                )
            )
        await self._commit()
        return call.status.value


@dataclass(frozen=True, kw_only=True)
class PauseCall(Command):
    """«Пауза» обучающегося (п. 3.7, безопасность): звонок мягко завершается и не оценивается блоком «Работа с
    заявителем». Нужна прежде всего для профилей `sensitive` (INACSL, SPRC 2024 — docs/research/psychology/04 §5)."""

    actor: Principal
    call_id: UUID
    meta: RequestMeta = field(default_factory=RequestMeta)


class PauseCallHandler(_CallBase):
    def __init__(self, *args: object, audit: AuditRecorder, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._audit = audit

    async def __call__(self, cmd: PauseCall) -> str:
        call = await self._own_call(cmd.call_id, cmd.actor)
        if call.psy is not None:
            call.psy = {**call.psy, "paused": True}
        if call.ended_at is None:
            await self._say(call, Speaker.SYSTEM, "Звонок остановлен обучающимся (пауза)")
        call.end(self._clock.now(), by="operator")
        await self._calls.save(call)
        await self._audit.record(
            AuditEntry(
                event=AuditEvent.CALL_PAUSED,
                actor=cmd.actor,
                meta=cmd.meta,
                description="Учебный звонок остановлен обучающимся"
                + (f" (профиль: {call.psy.get('title')})" if call.psy else ""),
                object_type="call",
                object_id=str(call.id),
                data={"psy_profile": (call.psy or {}).get("profile")},
            )
        )
        await self._commit()
        return call.status.value
