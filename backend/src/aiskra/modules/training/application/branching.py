"""Ведущий ветвления (F5, ADR-0014): ход ситуации в учебном звонке.

Факты для переходов собираются из звонка (что сказал оператор и когда, что уже сообщил заявитель) и из карточки 112
(когда сохранена, с какими службами, статусы ДДС). Шаг ветвления делается до ответа заявителя, рядом с шагом
психологического профиля, и по таймеру (`POST /calls/{id}/tick`). Новый узел меняет поведение заявителя: что
происходит сейчас и обновлённые факты уходят в промпт, а реплика-событие узла («Дым уже в коридоре!») звучит один раз.
Итог и разбор пересчитываются по всем фактам целиком (`resolve`) — в звонке, в оценке и в докладе бригады одинаково.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import datetime
from hashlib import sha1
from typing import Any

from aiskra.modules.training.application.ports.scenarios import CardContextSource, CardTimeline
from aiskra.modules.training.domain.branching import (
    BranchState,
    Facts,
    Node,
    Template,
    debrief,
    detect,
    entered,
    facts_from_json,
    from_snapshot,
    merged_legend,
    note_first,
    outcome_of,
    resolve,
    state_from_json,
    state_to_json,
)
from aiskra.modules.training.domain.call import Call
from aiskra.modules.training.domain.tone import CallerTone, ToneChange


@dataclass(frozen=True)
class BranchTurn:
    """Что изменил шаг ветвления для ответа заявителя."""

    template: Template
    node: Node
    entered: list[Node]
    legend: dict[str, Any]  # легенда с фактами текущего узла
    branch: dict[str, Any]  # новое содержимое call.branch
    said: list[str] = field(default_factory=list)  # инструкции, распознанные в этой реплике

    @property
    def situation(self) -> str:
        return self.node.situation

    @property
    def gates(self) -> frozenset[str]:
        return self.node.gates

    @property
    def escalate(self) -> int:
        return sum(n.escalate for n in self.entered)

    @property
    def events(self) -> list[str]:
        return [n.event for n in self.entered if n.event]


def start_branch(snapshot: dict[str, Any], weight: float) -> dict[str, Any]:
    """Ход ветвления нового звонка: шаблон из сценария, вес блока в оценке — снимок настроек занятия."""
    tpl = from_snapshot(snapshot)
    return {
        "template": tpl.id,
        "weight": float(weight),
        "said": {},
        "asked": {},
        "acts": {},
        "state": state_to_json(resolve(tpl, Facts(), 0.0)),
    }


def situation_change(node: Node, delta: int) -> ToneChange:
    """Ситуация изменила состояние заявителя: хуже — тревожнее и меньше готов отвечать, лучше — спокойнее."""
    return ToneChange("situation", node.title, tension=2 * delta, trust=0, readiness=-delta)


def shift_tone(tone: CallerTone, node: Node, delta: int) -> list[ToneChange]:
    if delta == 0:
        return []
    change = situation_change(node, delta)
    tone.tension = max(0, min(10, tone.tension + change.tension))
    tone.readiness = max(0, min(10, tone.readiness + change.readiness))
    return [change]


def shift_psy(psy: dict[str, Any], delta: int) -> dict[str, Any]:
    """Сдвиг уровня психологического профиля (ECCS 1–5) событием ситуации; нижняя граница — пол профиля."""
    if delta == 0:
        return psy
    state = dict(psy.get("state") or {})
    floor = int(psy.get("floor") or 1)
    level = max(floor, min(5, int(state.get("level", 2)) + delta))
    state["level"] = level
    state["peak"] = max(int(state.get("peak", level)), level)
    return {**psy, "state": state}


class BranchDirector:
    def __init__(self, cards: CardContextSource) -> None:
        self._cards = cards
        self._cache: dict[str, Template] = {}

    def template(self, snapshot: dict[str, Any]) -> Template:
        key = sha1(json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if key not in self._cache:
            self._cache[key] = from_snapshot(snapshot)
        return self._cache[key]

    @staticmethod
    def _elapsed(call: Call, at: datetime | None) -> float | None:
        begin = call.answered_at or call.started_at
        return None if at is None else max(0.0, (at - begin).total_seconds())

    async def timeline(self, call: Call) -> CardTimeline | None:
        return await self._cards.card_timeline(call.card_id) if call.card_id else None

    def facts(self, call: Call, timeline: CardTimeline | None) -> Facts:
        base = facts_from_json(call.branch)
        dds = {s: self._elapsed(call, at) for s, at in (timeline.statuses if timeline else {}).items()}
        return replace(
            base,
            card_saved_s=self._elapsed(call, timeline.saved_at) if timeline else None,
            services=timeline.services if timeline and timeline.saved_at else frozenset(),
            dds={k: v for k, v in dds.items() if v is not None},
            ended_s=self._elapsed(call, call.ended_at),
        )

    async def advance(
        self, call: Call, snapshot: dict[str, Any], legend: dict[str, Any], now: datetime, text: str | None = None
    ) -> BranchTurn | None:
        """Шаг ситуации к моменту `now`: реплика оператора (если есть) добавляет сказанные инструкции."""
        if call.branch is None or call.answered_at is None:
            return None
        tpl = self.template(snapshot)
        at = self._elapsed(call, now) or 0.0
        said = detect(tpl, text) if text else []
        branch = {
            **call.branch,
            "said": note_first(call.branch.get("said") or {}, said, at),
            "asked": note_first(call.branch.get("asked") or {}, [t for t in call.revealed if t != "opening"], at),
        }
        probe = replace(call, branch=branch)
        facts = self.facts(probe, await self.timeline(call))
        before = state_from_json(call.branch.get("state"), tpl)
        after = resolve(tpl, facts, at, before)
        new = [tpl.nodes[n] for n in entered(before, after)]
        branch["state"] = state_to_json(after)
        node = tpl.nodes[after.node]
        return BranchTurn(
            template=tpl, node=node, entered=new, legend=merged_legend(legend, node), branch=branch, said=said
        )

    def note_revealed(self, call: Call, now: datetime) -> None:
        """Темы, которые заявитель сообщил этим ответом, — с отметкой времени (условие `asked`)."""
        if call.branch is None:
            return
        at = self._elapsed(call, now) or 0.0
        call.branch = {
            **call.branch,
            "asked": note_first(call.branch.get("asked") or {}, [t for t in call.revealed if t != "opening"], at),
        }

    def note_acts(self, call: Call, acts: list[str], now: datetime) -> None:
        if call.branch is None or not acts:
            return
        at = self._elapsed(call, now) or 0.0
        call.branch = {**call.branch, "acts": note_first(call.branch.get("acts") or {}, acts, at)}

    async def view(self, call: Call, snapshot: dict[str, Any], now: datetime) -> dict[str, Any]:
        """«Итог ситуации»: пересчёт по всем фактам. Итог окончательный, когда разговор завершён и карточка
        сохранена (или карточки нет); до того — ситуация на текущий момент."""
        tpl = self.template(snapshot)
        timeline = await self.timeline(call)
        facts = self.facts(call, timeline)
        final = call.ended_at is not None and (call.card_id is None or (timeline is not None and timeline.saved_at))
        until = tpl.horizon_s if final else (self._elapsed(call, now) or 0.0)
        state: BranchState = resolve(tpl, facts, until)
        out = debrief(tpl, state, facts)
        out["final"] = bool(final and outcome_of(tpl, state) is not None)
        out["weight"] = float((call.branch or {}).get("weight") or 0)
        return out
