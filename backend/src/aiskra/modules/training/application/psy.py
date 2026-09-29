"""Ведущий психологического модификатора (п. 3.7, ADR-0012): один ход разговора с заявителем в стрессе.

Шаг: действия оператора (офлайн-словарь, по флагу — ИИ-задача PSY_ACTS) → движок состояния → ворота раскрытия →
реплика (модель по промпту applicant_actor/v3 или офлайн-шаблон профиля) → проверка → голос. Всё, что нужно для
оценки и разбора, пишется в `meta` реплик.

Голос. Синтез и распознавание речи делаются отдельным модулем; под полнодуплексный голосовой канал нужен адаптер.
Контракт для него — `TurnSignals` на входе (задержка ответа, перебивание — их меряет голосовой канал) и `PsyTurn.voice`
на выходе (темп, тон, громкость, невербальные вставки). Текстовый режим работает без адаптера: сигналов просто нет.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, replace
from typing import Any

from aiskra.modules.training.application.actors import Actors, PsyPrompt
from aiskra.modules.training.application.ports.psy import PsyCatalog
from aiskra.modules.training.domain.actors import applicant_reply
from aiskra.modules.training.domain.call import CallMessage, Speaker
from aiskra.modules.training.domain.psy import (
    ACT_TITLES,
    ALL_ACTS,
    LEVEL_TITLES,
    TOPICS,
    PsyProfile,
    PsyState,
    call_rng,
    gates,
    initial_state,
    step,
    tone_changes,
    tone_from_psy,
    voice_for,
)
from aiskra.modules.training.domain.psy_acts import Act, ActContext, classify_offline, norm
from aiskra.modules.training.domain.psy_render import (
    distort_address,
    offline_reply,
    opening_line,
    parse_remarks,
    validate,
)
from aiskra.modules.training.domain.tone import CallerTone, ToneSnapshot

log = logging.getLogger(__name__)
COMPLY_LOW = ("Хорошо… делаю.", "Да, сейчас сделаю.", "Хорошо, так и делаю.")
COMPLY_HIGH = ("Я не могу… я не понимаю, что делать!", "Что? Как?! Я не могу!")


@dataclass(frozen=True)
class TurnSignals:
    """Сигналы голосового канала для хода. Передаёт голосовой или дуплекс-адаптер; в текстовом режиме — пусто."""

    latency_ms: int | None = None  # от конца реплики заявителя до начала ответа оператора
    interrupted: bool = False  # оператор заговорил, пока звучала реплика заявителя


@dataclass(frozen=True)
class PsyTurn:
    text: str  # что произносит заявитель (без ремарок)
    remarks: list[str]
    voice: dict[str, Any]
    hung_up: bool
    revealed: list[str]
    psy: dict[str, Any]  # новое содержимое call.psy
    tone: CallerTone | None = None  # голосовое состояние заявителя (выведено из профиля) — для синтеза речи
    snapshot: ToneSnapshot | None = None  # снимок у этой реплики
    operator_meta: dict[str, Any] = field(default_factory=dict)
    party_meta: dict[str, Any] = field(default_factory=dict)


def start_psy(
    p: PsyProfile, *, seed: int, catalog_version: int, settings: dict[str, Any], session_id: str | None
) -> dict[str, Any]:
    """Снимок профиля для звонка + начальное состояние."""
    return {
        **p.snapshot(),
        "catalog_version": catalog_version,
        "seed": seed,
        "intensity": int(settings.get("intensity", 2)),
        "weight": float(settings.get("weight", 0.0)),
        "llm_acts": bool(settings.get("llm_acts", False)),
        "session_id": session_id,
        "applicant_status": p.applicant_status,
        "paused": False,
        "state": initial_state(p).to_dict(),
    }


def _legend(legend: dict[str, Any], psy: dict[str, Any]) -> dict[str, Any]:
    status = psy.get("applicant_status")
    if not status:
        return legend
    return {**legend, "applicant": {**(legend.get("applicant") or {}), "status": status}}


def _address_tokens(legend: dict[str, Any]) -> tuple[str, ...]:
    a = legend.get("address") or {}
    street = norm(str(a.get("street") or ""))
    words = [w for w in re.findall(r"[а-яa-z]+", street) if len(w) >= 4 and w not in ("улица", "проспект", "переулок")]
    house = str(a.get("house") or "").strip().lower()
    return tuple(w for w in (*(words[:1]), house) if w)


class PsyDirector:
    def __init__(self, catalog: PsyCatalog, actors: Actors) -> None:
        self.catalog = catalog
        self._actors = actors

    def profile(self, psy: dict[str, Any] | None) -> PsyProfile | None:
        return self.catalog.get(str(psy.get("profile"))) if psy else None

    def opening(
        self, psy: dict[str, Any], legend: dict[str, Any]
    ) -> tuple[str, list[str], dict[str, Any], CallerTone] | None:
        p = self.profile(psy)
        if p is None:
            return None
        state = PsyState.from_dict(psy["state"])
        text, remarks = parse_remarks(opening_line(p, _legend(legend, psy), call_rng(int(psy["seed"]), 0)))
        voice = voice_for(p, state, remarks, int(psy.get("intensity", 2)))
        tone = tone_from_psy(p, state, whisper="шёпотом" in remarks)
        meta = {"level": state.level, "remarks": remarks, "voice": voice, "source": "offline", "emotional": True}
        return text, remarks, meta, tone

    async def turn(
        self,
        psy: dict[str, Any],
        legend: dict[str, Any],
        history: list[CallMessage],
        question: str,
        revealed: list[str],
        elapsed_s: float,
        signals: TurnSignals,
        scope: str,
    ) -> PsyTurn | None:
        p = self.profile(psy)
        if p is None:  # профиль убрали из каталога — звонок продолжается без модификатора
            return None
        legend = _legend(legend, psy)
        before = PsyState.from_dict(psy["state"])
        operator_before = [m.text for m in history if m.speaker is Speaker.OPERATOR]
        name = str((legend.get("applicant") or {}).get("name") or "").split()
        ctx = ActContext(
            first_turn=not operator_before,
            applicant_first_name=name[1] if "name" in revealed and len(name) > 1 else None,
            revealed=frozenset(revealed),
            confirmed=frozenset(before.confirmed),
            address_tokens=_address_tokens(legend) if "address" in revealed else (),
            previous_operator=tuple(operator_before),
            persist_run=before.persist,
        )
        acts = classify_offline(question, ctx)
        source_acts = "offline"
        if psy.get("llm_acts"):
            llm = await self._actors.classify_acts(question, context=f"профиль: {p.title}; уровень {before.level}")
            if llm is not None:
                seen = {a.code for a in acts}
                acts += [Act(c, q) for c, q in llm if c in ALL_ACTS and c not in seen]
                source_acts = "offline+llm"
        if signals.latency_ms is not None and signals.latency_ms > p.dead_air_s * 1000:
            acts.append(Act("DEAD_AIR", f"{signals.latency_ms / 1000:.0f} с"))
        if signals.interrupted:
            acts.append(Act("INTERRUPT", ""))
        codes = {a.code for a in acts}

        state, deltas = step(p, before, codes, elapsed_s, call_rng(int(psy["seed"]), before.turn + 1))
        state.persist = before.persist + 1 if "REPEAT_PERSIST" in codes else 0
        allowed = gates(p, state)
        base = applicant_reply(legend, question, revealed)
        if codes & {"INSTRUCT", "BREATHING"} and not codes & {"ASK_CLOSED", "ASK_OPEN", "ASK_CHOICE", "ASK_SUICIDE"}:
            # инструкция без вопроса: заявитель выполняет или, если он в пике, не может (а не отвечает «про этаж»)
            comply = COMPLY_LOW if state.level <= 3 else COMPLY_HIGH
            base = replace(base, text=comply[state.turn % len(comply)], topic=None, revealed=list(revealed))
        blocked = base.topic is not None and base.topic not in allowed
        new_revealed = revealed if blocked else base.revealed
        house = str((legend.get("address") or {}).get("house") or "")
        base_text = distort_address(p, state, base.text, house) if base.topic == "address" else base.text

        text: str | None = None
        source = "offline"
        if not state.hung_up:
            prompt = PsyPrompt(
                profile_title=p.title,
                level=state.level,
                level_title=LEVEL_TITLES[state.level],
                speech=p.speech.get(state.level, ""),
                rules=p.rules,
                intensity=int(psy.get("intensity", 2)),
                allowed=[t for t in TOPICS if t in allowed],
                blocked=[t for t in TOPICS if t not in allowed],
            )
            cache_scope = f"{scope}:{p.id}:{state.level}:{state.stage}:{','.join(sorted(new_revealed))}"
            text = await self._actors.applicant_psy(legend, history, question, prompt, cache_scope)
            if text:
                reason = validate(text, legend=legend, allowed=allowed, intensity=prompt.intensity)
                if reason:
                    log.info("Реплика модели отклонена (%s) — офлайн-реплика профиля", reason)
                    text = None
                else:
                    source = "llm"
        if not text:
            text = offline_reply(
                p,
                state,
                base=base_text,
                topic=base.topic,
                allowed=allowed,
                legend=legend,
                rng=call_rng(int(psy["seed"]), 10_000 + state.turn),
            )
        clean, remarks = parse_remarks(text)
        if state.hung_up and "кладёт трубку" not in remarks:
            remarks.append("кладёт трубку")
        voice = voice_for(p, state, remarks, int(psy.get("intensity", 2)))
        operator_meta = {
            "acts": [{"code": a.code, "quote": a.quote, "title": ACT_TITLES.get(a.code, a.code)} for a in acts],
            "acts_source": source_acts,
            "level_before": before.level,
            "level_after": state.level,
            "deltas": [{"cause": d.cause, "change": d.change, "note": d.note} for d in deltas],
            "topic": base.topic,
            "elapsed_s": round(elapsed_s, 1),
            "signals": {"latency_ms": signals.latency_ms, "interrupted": signals.interrupted},
        }
        party_meta = {
            "level": state.level,
            "stage": state.stage,
            "remarks": remarks,
            "voice": voice,
            "blocked": base.topic if blocked else None,
            "emotional": state.level >= 3 or bool({"плачет", "кричит", "задыхается"} & set(remarks)),
            "source": source,
        }
        tone = tone_from_psy(p, state, whisper="шёпотом" in remarks)
        return PsyTurn(
            tone=tone,
            snapshot=tone.snapshot(tone_changes(deltas)),
            text=clean,
            remarks=remarks,
            voice=voice,
            hung_up=state.hung_up,
            revealed=new_revealed,
            psy={**psy, "state": state.to_dict()},
            operator_meta=operator_meta,
            party_meta=party_meta,
        )
