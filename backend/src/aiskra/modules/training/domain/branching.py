"""Ветвящиеся сценарии (F5, ADR-0014): граф ситуации и детерминированный движок.

Ситуация — граф из шаблона (`data/dictionaries/branch_templates.yaml`): узел описывает, что происходит сейчас, переход —
при каком решении оператора 112 или ДДС ситуация меняется, конечный узел — итог. Состояние хранит этот модуль, а не
языковая модель: модель только озвучивает заданный узел, поэтому итог воспроизводим.

Факты для переходов — с отметками времени от ответа на вызов: что оператор сказал (`said`), что заявитель уже сообщил
(`asked`), действия оператора (`acts`), когда сохранена карточка и с какими службами, статусы ДДС, конец разговора.
`resolve` проходит все моменты, когда что-то могло измениться, по порядку и вызывает `step`. Поэтому один и тот же
ход звонка всегда даёт один и тот же путь, где бы его ни пересчитали: в звонке, в оценке или в докладе бригады.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from aiskra.modules.training.domain.psy import ALL_ACTS

OUTCOMES = ("favorable", "partial", "adverse", "tragic")
OUTCOME_TITLES = {
    "favorable": "благоприятный",
    "partial": "частично благоприятный",
    "adverse": "неблагоприятный",
    "tragic": "трагический",
}
OUTCOME_SCORE = {"favorable": 100.0, "partial": 60.0, "adverse": 30.0, "tragic": 0.0}
TOPICS = frozenset({"what", "address", "floor", "name", "phone", "victims", "danger", "access", "gas", "status"})
DDS_STATUSES = frozenset({"accepted", "response_started", "arrived", "works_in_progress", "works_completed"})
FACT_KEYS = frozenset({"what", "details", "danger", "access", "gas", "traffic", "victims_note"})
CONDITION_KEYS = frozenset({"said", "asked", "act", "after_s", "card_by_s", "service", "dds", "ended"})
MAX_HOPS = 16  # защита от зацикливания внутри одного шага


class BranchTemplateError(ValueError):
    """Ошибка в шаблоне ветвления: шаблон с ошибкой не загружается, приложение не стартует."""


# ------------------------------------------------------------------ шаблон


@dataclass(frozen=True)
class Source:
    code: str
    title: str
    url: str


@dataclass(frozen=True)
class Instruction:
    id: str
    title: str
    stems: tuple[str, ...]
    source: str
    harmful: bool = False


@dataclass(frozen=True)
class Condition:
    said: str | None = None
    asked: str | None = None
    act: str | None = None
    after_s: float | None = None
    card_by_s: float | None = None
    service: str | None = None
    dds: str | None = None
    ended: bool | None = None

    @property
    def timed_only(self) -> bool:
        """Только время: такой переход гарантирует, что ситуация сдвинется, даже если оператор ничего не сделал."""
        return self.after_s is not None and all(
            v is None for v in (self.said, self.asked, self.act, self.card_by_s, self.service, self.dds, self.ended)
        )


@dataclass(frozen=True)
class Edge:
    to: str
    when: Condition
    label: str  # решение оператора, как его видит разбор
    effect: str  # что из этого вышло
    source: str
    note: str = ""  # didactic — время перехода учебное


@dataclass(frozen=True)
class Outcome:
    code: str
    text: str
    sources: tuple[str, ...]

    @property
    def title(self) -> str:
        return OUTCOME_TITLES[self.code]


@dataclass(frozen=True)
class Node:
    id: str
    title: str
    situation: str = ""  # что происходит сейчас — для модели и разбора
    event: str = ""  # что заявитель говорит, когда ситуация доходит до узла
    escalate: int = 0  # сдвиг состояния заявителя: +1 — тревожнее, −1 — спокойнее
    gates: frozenset[str] = frozenset()  # темы, которые заявитель в этом узле может сообщить при любом состоянии
    facts: Mapping[str, str] = field(default_factory=dict)  # поверх легенды
    brigade: Mapping[str, str] = field(default_factory=dict)  # доклад старшего группы по статусу службы
    edges: tuple[Edge, ...] = ()
    outcome: Outcome | None = None


@dataclass(frozen=True)
class Check:
    """Контрольный ход звонка из шаблона: такие факты должны дать такой итог (проверяется тестами)."""

    name: str
    facts: Facts
    expect: str


@dataclass(frozen=True)
class Template:
    id: str
    title: str
    description: str
    incident_codes: tuple[str, ...]
    horizon_s: float
    start: str
    nodes: Mapping[str, Node]
    instructions: Mapping[str, Instruction]
    sources: Mapping[str, Source]
    legend: Mapping[str, Any]
    checks: tuple[Check, ...] = ()

    def source(self, code: str) -> Source:
        return self.sources[code]

    @property
    def forks(self) -> list[Node]:
        return [n for n in self.nodes.values() if len(n.edges) >= 2]

    @property
    def terminals(self) -> list[Node]:
        return [n for n in self.nodes.values() if n.outcome is not None]


# ------------------------------------------------------------------ факты и состояние


@dataclass(frozen=True)
class Facts:
    """Что произошло к моменту и когда (секунды от ответа на вызов)."""

    said: Mapping[str, float] = field(default_factory=dict)
    asked: Mapping[str, float] = field(default_factory=dict)
    acts: Mapping[str, float] = field(default_factory=dict)
    card_saved_s: float | None = None
    services: frozenset[str] = frozenset()
    dds: Mapping[str, float] = field(default_factory=dict)
    ended_s: float | None = None

    def moments(self) -> set[float]:
        times = {*self.said.values(), *self.asked.values(), *self.acts.values(), *self.dds.values()}
        for t in (self.card_saved_s, self.ended_s):
            if t is not None:
                times.add(t)
        return times


@dataclass(frozen=True)
class Step:
    node: str
    at_s: float
    via: int | None = None  # номер перехода в предыдущем узле; None — старт
    source_node: str | None = None


@dataclass(frozen=True)
class BranchState:
    node: str
    t: float = 0.0
    path: tuple[Step, ...] = ()

    @property
    def visited(self) -> list[str]:
        return [s.node for s in self.path]


def initial_state(tpl: Template) -> BranchState:
    return BranchState(node=tpl.start, t=0.0, path=(Step(tpl.start, 0.0),))


def holds(c: Condition, f: Facts, t: float) -> bool:
    """Условие перехода в момент `t` по фактам не позже `t`."""
    if c.after_s is not None and t < c.after_s:
        return False
    if c.said is not None and not (c.said in f.said and f.said[c.said] <= t):
        return False
    if c.asked is not None and not (c.asked in f.asked and f.asked[c.asked] <= t):
        return False
    if c.act is not None and not (c.act in f.acts and f.acts[c.act] <= t):
        return False
    saved = f.card_saved_s is not None and f.card_saved_s <= t
    if c.card_by_s is not None and not (saved and f.card_saved_s is not None and f.card_saved_s <= c.card_by_s):
        return False
    if c.service is not None and not (saved and c.service in f.services):
        return False
    if c.dds is not None and not (c.dds in f.dds and f.dds[c.dds] <= t):
        return False
    return c.ended is None or (f.ended_s is not None and f.ended_s <= t) == c.ended


def step(tpl: Template, state: BranchState, facts: Facts, t: float) -> BranchState:
    """Один шаг в момент `t`: переходы текущего узла по порядку, первый выполненный срабатывает; затем — переходы
    нового узла (цепочка), пока ни один не выполнен или не достигнут итог. В пределах шага узел не повторяется."""
    node, path, seen = state.node, list(state.path), {state.node}
    for _ in range(MAX_HOPS):
        current = tpl.nodes[node]
        if current.outcome is not None:
            break
        moved = False
        for i, edge in enumerate(current.edges):
            if edge.to not in seen and holds(edge.when, facts, t):
                path.append(Step(edge.to, t, via=i, source_node=node))
                node, moved = edge.to, True
                seen.add(node)
                break
        if not moved:
            break
    return BranchState(node=node, t=max(t, state.t), path=tuple(path))


def _thresholds(tpl: Template) -> set[float]:
    out: set[float] = set()
    for n in tpl.nodes.values():
        for e in n.edges:
            if e.when.after_s is not None:
                out.add(e.when.after_s)
    return out


def resolve(tpl: Template, facts: Facts, until_s: float, state: BranchState | None = None) -> BranchState:
    """Состояние к моменту `until_s`: шаги во все моменты, когда могло что-то измениться (пороги времени шаблона и
    отметки фактов), по порядку. Ход звонка → путь — чистая функция."""
    state = state or initial_state(tpl)
    until = min(until_s, tpl.horizon_s)
    moments = sorted(m for m in _thresholds(tpl) | facts.moments() | {until} if state.t <= m <= until)
    for m in moments:
        state = step(tpl, state, facts, m)
        if tpl.nodes[state.node].outcome is not None:
            break
    return state


def outcome_of(tpl: Template, state: BranchState) -> Outcome | None:
    return tpl.nodes[state.node].outcome


# ------------------------------------------------------------------ речь оператора


def _norm(text: str) -> str:
    return " ".join(text.lower().replace("ё", "е").split())


_NEG = re.compile(r"(^|\s)(не|ни)\s+$")


def detect(tpl: Template, text: str) -> list[str]:
    """Какие инструкции шаблона есть в реплике. Вредная инструкция с «не» перед ней («не открывайте окна») не
    засчитывается: основы вредных советов записаны в повелительной форме."""
    t = _norm(text)
    found: list[str] = []
    for ins in tpl.instructions.values():
        for stem in ins.stems:
            s = _norm(stem)
            start = t.find(s)
            while start >= 0:
                if not (ins.harmful and _NEG.search(t[max(0, start - 4) : start])):
                    found.append(ins.id)
                    break
                start = t.find(s, start + 1)
            if ins.id in found:
                break
    return found


# ------------------------------------------------------------------ разбор


@dataclass(frozen=True)
class Choice:
    label: str
    effect: str
    to: str
    to_title: str
    source: Source
    didactic: bool
    outcome: str | None  # итог, если переход ведёт прямо к нему


@dataclass(frozen=True)
class Fork:
    node: str
    title: str
    at_s: float  # когда ситуация пришла в узел
    decided_s: float | None  # когда выбран переход; None — ещё не выбран
    taken: Choice | None
    others: list[Choice]


def _choice(tpl: Template, e: Edge) -> Choice:
    target = tpl.nodes[e.to]
    return Choice(
        label=e.label,
        effect=e.effect,
        to=e.to,
        to_title=target.title,
        source=tpl.sources[e.source],
        didactic=e.note == "didactic",
        outcome=target.outcome.code if target.outcome else None,
    )


def forks(tpl: Template, state: BranchState) -> list[Fork]:
    """Развилки на пройденном пути: что выбрано и что было бы при другом решении."""
    out: list[Fork] = []
    for i, s in enumerate(state.path):
        node = tpl.nodes[s.node]
        if len(node.edges) < 2:
            continue
        nxt = state.path[i + 1] if i + 1 < len(state.path) else None
        taken_i = nxt.via if nxt is not None else None
        out.append(
            Fork(
                node=node.id,
                title=node.title,
                at_s=s.at_s,
                decided_s=nxt.at_s if nxt else None,
                taken=_choice(tpl, node.edges[taken_i]) if taken_i is not None else None,
                others=[_choice(tpl, e) for j, e in enumerate(node.edges) if j != taken_i],
            )
        )
    return out


def debrief(tpl: Template, state: BranchState, facts: Facts) -> dict[str, Any]:
    """«Итог ситуации» для интерфейса и оценки: итог, путь, развилки, время ключевых решений."""
    outcome = outcome_of(tpl, state)
    used: set[str] = set()
    for f in forks(tpl, state):
        for c in [f.taken, *f.others]:
            if c is not None:
                used.add(c.source.code)
    if outcome:
        used.update(outcome.sources)
    return {
        "template": tpl.id,
        "title": tpl.title,
        "node": state.node,
        "node_title": tpl.nodes[state.node].title,
        "situation": tpl.nodes[state.node].situation,
        "brigade": dict(tpl.nodes[state.node].brigade),  # доклад старшего группы по статусу (RF5-04)
        "outcome": {
            "code": outcome.code,
            "title": outcome.title,
            "text": outcome.text,
            "sources": list(outcome.sources),
        }
        if outcome
        else None,
        "path": [{"node": s.node, "title": tpl.nodes[s.node].title, "at_s": round(s.at_s, 1)} for s in state.path],
        "forks": [_fork_json(f) for f in forks(tpl, state)],
        "decisions": {
            **{f"said:{k}": round(v, 1) for k, v in sorted(facts.said.items(), key=lambda x: x[1])},
            **({"card_saved": round(facts.card_saved_s, 1)} if facts.card_saved_s is not None else {}),
            **{f"asked:{k}": round(v, 1) for k, v in facts.asked.items() if k == "address"},
        },
        "instructions": [
            {"id": i.id, "title": i.title, "harmful": i.harmful, "said_s": facts.said.get(i.id), "source": i.source}
            for i in tpl.instructions.values()
        ],
        "sources": {c: {"title": tpl.sources[c].title, "url": tpl.sources[c].url} for c in sorted(used)},
    }


def _choice_json(c: Choice | None) -> dict[str, Any] | None:
    if c is None:
        return None
    return {
        "label": c.label,
        "effect": c.effect,
        "to": c.to,
        "to_title": c.to_title,
        "source": c.source.code,
        "didactic": c.didactic,
        "outcome": c.outcome,
    }


def _fork_json(f: Fork) -> dict[str, Any]:
    return {
        "node": f.node,
        "title": f.title,
        "at_s": round(f.at_s, 1),
        "decided_s": round(f.decided_s, 1) if f.decided_s is not None else None,
        "taken": _choice_json(f.taken),
        "others": [_choice_json(c) for c in f.others],
    }


# ------------------------------------------------------------------ разбор шаблона и проверка графа


def _str(raw: Mapping[str, Any], key: str, where: str, default: str | None = None) -> str:
    v = raw.get(key, default)
    if not isinstance(v, str) or (default is None and not v.strip()):
        raise BranchTemplateError(f"{where}: нужен текст «{key}»")
    return v


def parse_facts(raw: Mapping[str, Any]) -> Facts:
    card = raw.get("card") or {}
    return Facts(
        said={str(k): float(v) for k, v in (raw.get("said") or {}).items()},
        asked={str(k): float(v) for k, v in (raw.get("asked") or {}).items()},
        acts={str(k): float(v) for k, v in (raw.get("acts") or {}).items()},
        card_saved_s=float(card["saved_s"]) if card.get("saved_s") is not None else None,
        services=frozenset(str(s) for s in card.get("services") or []),
        dds={str(k): float(v) for k, v in (raw.get("dds") or {}).items()},
        ended_s=float(raw["ended_s"]) if raw.get("ended_s") is not None else None,
    )


def _condition(raw: Mapping[str, Any], where: str) -> Condition:
    unknown = set(raw) - CONDITION_KEYS
    if unknown or not raw:
        raise BranchTemplateError(f"{where}: условие пустое или с неизвестными ключами {sorted(unknown)}")
    return Condition(
        said=str(raw["said"]) if "said" in raw else None,
        asked=str(raw["asked"]) if "asked" in raw else None,
        act=str(raw["act"]) if "act" in raw else None,
        after_s=float(raw["after_s"]) if "after_s" in raw else None,
        card_by_s=float(raw["card_by_s"]) if "card_by_s" in raw else None,
        service=str(raw["service"]) if "service" in raw else None,
        dds=str(raw["dds"]) if "dds" in raw else None,
        ended=bool(raw["ended"]) if "ended" in raw else None,
    )


def parse_template(tid: str, raw: Mapping[str, Any], sources: Mapping[str, Any]) -> Template:
    """Шаблон из YAML (или копия из сценария) → неизменяемая модель. Проверка графа — `validate_graph`."""
    where = f"шаблон {tid}"
    src = {
        code: Source(code, _str(s, "title", f"источник {code}"), str(s.get("url") or ""))
        for code, s in (sources or {}).items()
    }
    instructions = {}
    for iid, i in (raw.get("instructions") or {}).items():
        stems = tuple(str(x) for x in i.get("stems") or [])
        if not stems:
            raise BranchTemplateError(f"{where}, инструкция {iid}: нет основ слов")
        instructions[iid] = Instruction(
            id=iid,
            title=_str(i, "title", f"{where}, инструкция {iid}"),
            stems=stems,
            source=_str(i, "source", f"{where}, инструкция {iid}"),
            harmful=bool(i.get("harmful", False)),
        )
    nodes = {}
    for nid, n in (raw.get("nodes") or {}).items():
        w = f"{where}, узел {nid}"
        edges = tuple(
            Edge(
                to=_str(e, "to", w),
                when=_condition(e.get("when") or {}, f"{w}, переход {i + 1}"),
                label=_str(e, "label", w),
                effect=_str(e, "effect", w),
                source=_str(e, "source", w),
                note=str(e.get("note") or ""),
            )
            for i, e in enumerate(n.get("edges") or [])
        )
        o = n.get("outcome")
        outcome = (
            Outcome(code=_str(o, "code", w), text=_str(o, "text", w), sources=tuple(o.get("sources") or ()))
            if o
            else None
        )
        nodes[nid] = Node(
            id=nid,
            title=_str(n, "title", w),
            situation=str(n.get("situation") or ""),
            event=str(n.get("event") or ""),
            escalate=int(n.get("escalate", 0)),
            gates=frozenset(str(g) for g in n.get("gates") or []),
            facts={str(k): str(v) for k, v in (n.get("facts") or {}).items()},
            brigade={str(k): str(v) for k, v in (n.get("brigade") or {}).items()},
            edges=edges,
            outcome=outcome,
        )
    checks = tuple(
        Check(name=name, facts=parse_facts(c), expect=_str(c, "expect", f"{where}, проверка {name}"))
        for name, c in (raw.get("checks") or {}).items()
    )
    return Template(
        id=tid,
        title=_str(raw, "title", where),
        description=str(raw.get("description") or ""),
        incident_codes=tuple(str(c) for c in raw.get("incident_codes") or ()),
        horizon_s=float(raw.get("horizon_s", 600)),
        start=_str(raw, "start", where),
        nodes=nodes,
        instructions=instructions,
        sources=src,
        legend=dict(raw.get("legend") or {}),
        checks=checks,
    )


def validate_graph(tpl: Template) -> list[str]:
    """Ошибки графа: недостижимые узлы, тупики без итога, циклы без времени, неизвестные ссылки и коды."""
    errors: list[str] = []
    w = f"шаблон {tpl.id}"
    if tpl.start not in tpl.nodes:
        return [f"{w}: нет стартового узла {tpl.start}"]
    for n in tpl.nodes.values():
        if n.outcome is not None:
            if n.edges:
                errors.append(f"{w}, узел {n.id}: у итога не может быть переходов")
            if n.outcome.code not in OUTCOMES:
                errors.append(f"{w}, узел {n.id}: итог {n.outcome.code} не из {OUTCOMES}")
            errors += [f"{w}, узел {n.id}: нет источника {s}" for s in n.outcome.sources if s not in tpl.sources]
            if not n.outcome.sources:
                errors.append(f"{w}, узел {n.id}: у итога нет источника")
            continue
        if not n.edges:
            errors.append(f"{w}, узел {n.id}: тупик без итога")
        if not any(e.when.timed_only for e in n.edges):
            errors.append(f"{w}, узел {n.id}: нет перехода по времени — ситуация может зависнуть без итога")
        if n.gates - TOPICS:
            errors.append(f"{w}, узел {n.id}: неизвестные темы ворот {sorted(n.gates - TOPICS)}")
        if set(n.facts) - FACT_KEYS:
            errors.append(f"{w}, узел {n.id}: неизвестные факты {sorted(set(n.facts) - FACT_KEYS)}")
        for e in n.edges:
            ew = f"{w}, узел {n.id} → {e.to}"
            if e.to not in tpl.nodes:
                errors.append(f"{ew}: нет такого узла")
            if e.source not in tpl.sources:
                errors.append(f"{ew}: нет источника {e.source}")
            c = e.when
            if c.said is not None and c.said not in tpl.instructions:
                errors.append(f"{ew}: нет инструкции {c.said}")
            if c.asked is not None and c.asked not in TOPICS:
                errors.append(f"{ew}: нет темы {c.asked}")
            if c.act is not None and c.act not in ALL_ACTS:
                errors.append(f"{ew}: нет действия {c.act}")
            if c.dds is not None and c.dds not in DDS_STATUSES:
                errors.append(f"{ew}: нет статуса ДДС {c.dds}")
            if c.after_s is not None and c.after_s > tpl.horizon_s:
                errors.append(f"{ew}: время {c.after_s} с дальше горизонта {tpl.horizon_s} с")
    for i in tpl.instructions.values():
        if i.source not in tpl.sources:
            errors.append(f"{w}, инструкция {i.id}: нет источника {i.source}")
    if errors:
        return errors
    reachable = _reachable(tpl, tpl.start)
    errors += [f"{w}: узел {n} недостижим" for n in tpl.nodes if n not in reachable]
    for n in tpl.nodes.values():
        if not any(tpl.nodes[x].outcome is not None for x in _reachable(tpl, n.id)):
            errors.append(f"{w}, узел {n.id}: из него не достичь итога")
    cycle = _untimed_cycle(tpl)
    if cycle:
        errors.append(f"{w}: цикл без перехода по времени: {' → '.join(cycle)}")
    return errors


def _reachable(tpl: Template, start: str) -> set[str]:
    seen, stack = {start}, [start]
    while stack:
        for e in tpl.nodes[stack.pop()].edges:
            if e.to not in seen:
                seen.add(e.to)
                stack.append(e.to)
    return seen


def _untimed_cycle(tpl: Template) -> list[str]:
    """Цикл, в котором нет ни одного перехода с условием времени, — такой цикл мог бы крутиться без конца."""
    graph = {n.id: [e.to for e in n.edges if e.when.after_s is None] for n in tpl.nodes.values()}
    color: dict[str, int] = {}
    stack: list[str] = []

    def visit(v: str) -> list[str]:
        color[v] = 1
        stack.append(v)
        for u in graph[v]:
            if color.get(u) == 1:
                return [*stack[stack.index(u) :], u]
            if color.get(u) is None:
                found = visit(u)
                if found:
                    return found
        stack.pop()
        color[v] = 2
        return []

    for v in graph:
        if color.get(v) is None:
            found = visit(v)
            if found:
                return found
    return []


def parse_catalog(raw: Mapping[str, Any]) -> tuple[int, dict[str, Template]]:
    """Каталог шаблонов: каждый шаблон разбирается и проверяется; ошибка — исключение со списком."""
    sources = raw.get("sources") or {}
    out: dict[str, Template] = {}
    errors: list[str] = []
    for tid, t in (raw.get("templates") or {}).items():
        tpl = parse_template(tid, t, sources)
        errors += validate_graph(tpl)
        out[tid] = tpl
    if errors:
        raise BranchTemplateError("; ".join(errors))
    return int(raw.get("version", 1)), out


# ------------------------------------------------------------------ копия шаблона в сценарий


def _fill(value: Any, params: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        out = value
        for k, v in params.items():
            out = out.replace("{" + k + "}", v)
        return out
    if isinstance(value, list):
        return [_fill(x, params) for x in value]
    if isinstance(value, dict):
        return {k: _fill(v, params) for k, v in value.items()}
    return value


def instantiate(
    tid: str, raw: Mapping[str, Any], sources: Mapping[str, Any], legend: Mapping[str, Any]
) -> dict[str, Any]:
    """Копия шаблона для сценария (`scenarios.branching`): плейсхолдеры заполнены по легенде, источники вложены, чтобы
    сценарий не зависел от правок каталога. Проверки (`checks`) в копию не входят."""
    address = legend.get("address") or {}
    params = {"floor": str(address.get("floor") or ""), "address": str(address.get("label") or "")}
    body = {k: v for k, v in raw.items() if k != "checks"}
    used = {i.get("source") for i in (raw.get("instructions") or {}).values()}
    for n in (raw.get("nodes") or {}).values():
        used.update(e.get("source") for e in n.get("edges") or [])
        used.update((n.get("outcome") or {}).get("sources") or [])
    return {
        "id": tid,
        **_fill(body, params),
        "sources": {c: dict(sources[c]) for c in sorted(x for x in used if x in sources)},
    }


def from_snapshot(snapshot: Mapping[str, Any]) -> Template:
    """Шаблон из копии в сценарии."""
    return parse_template(str(snapshot["id"]), snapshot, snapshot.get("sources") or {})


def apply_texts(snapshot: dict[str, Any], texts: Mapping[str, str]) -> dict[str, Any]:
    """Формулировки реплик-событий под легенду (RF5-09): меняется только `event` узлов, структура — нет."""
    nodes = {
        nid: ({**n, "event": texts[nid]} if nid in texts and n.get("event") else n)
        for nid, n in snapshot["nodes"].items()
    }
    return {**snapshot, "nodes": nodes}


def event_nodes(snapshot: Mapping[str, Any]) -> dict[str, str]:
    return {nid: str(n["event"]) for nid, n in (snapshot.get("nodes") or {}).items() if n.get("event")}


def merged_legend(legend: Mapping[str, Any], node: Node) -> dict[str, Any]:
    """Легенда с фактами узла: заявитель рассказывает о ситуации, какой она стала."""
    if not node.facts:
        return dict(legend)
    facts = {**(legend.get("facts") or {}), **{k: v for k, v in node.facts.items() if k not in ("what", "details")}}
    out = {**legend, "facts": facts}
    for k in ("what", "details"):
        if k in node.facts:
            out[k] = node.facts[k]
    return out


def entered(before: BranchState, after: BranchState) -> list[str]:
    """Узлы, в которые ситуация пришла за шаг (по порядку)."""
    return [s.node for s in after.path[len(before.path) :]]


def state_from_json(raw: Mapping[str, Any] | None, tpl: Template) -> BranchState:
    if not raw or not raw.get("path"):
        return initial_state(tpl)
    path = tuple(
        Step(str(s["node"]), float(s["at_s"]), s.get("via"), s.get("from"))
        for s in raw["path"]
        if s["node"] in tpl.nodes
    )
    return BranchState(node=path[-1].node, t=float(raw.get("t", path[-1].at_s)), path=path)


def state_to_json(state: BranchState) -> dict[str, Any]:
    return {
        "node": state.node,
        "t": state.t,
        "path": [{"node": s.node, "at_s": s.at_s, "via": s.via, "from": s.source_node} for s in state.path],
    }


def facts_from_json(raw: Mapping[str, Any] | None) -> Facts:
    raw = raw or {}
    return Facts(
        said={str(k): float(v) for k, v in (raw.get("said") or {}).items()},
        asked={str(k): float(v) for k, v in (raw.get("asked") or {}).items()},
        acts={str(k): float(v) for k, v in (raw.get("acts") or {}).items()},
    )


def note_first(times: Mapping[str, float], keys: Iterable[str], at_s: float) -> dict[str, float]:
    """Первое время для каждого ключа: факт «сказал» не сдвигается более поздним повтором."""
    out = dict(times)
    for k in keys:
        out.setdefault(k, at_s)  # без округления: округление вверх сдвинуло бы факт позже момента шага
    return out
