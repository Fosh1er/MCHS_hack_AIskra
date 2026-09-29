"""Психологический модификатор сценария (п. 3.6, ADR-0011): профиль заявителя и детерминированный движок состояния.

Состояние заявителя хранит не языковая модель, а этот модуль: уровень по шкале ECCS IAED 1–5 (Clawson & Sinclair
2001), доверие к оператору и этап (для кризисных профилей). Уровень меняется по действиям оператора
(`psy_acts.py`): запрещённое действие поднимает его сразу, снижение требует нескольких правильных действий подряд
(асимметрия — SimPatient, CARS, ResistClient; docs/research/psychology/04 §1). Уровень задаёт, какие темы легенды
заявитель может сообщить («ворота»), и как звучит голос. Модель только «играет» заданное состояние, поэтому оценка
воспроизводима: одинаковые действия при одном seed дают одну траекторию.

Предметная основа — docs/research/psychology/06_Каталог_состояний_заявителя.md, каталог — data/dictionaries.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

# ------------------------------------------------------------------ словари

GOOD_ACTS = frozenset(
    {
        "GREET",
        "NAME_USE",
        "ASK_CLOSED",
        "ASK_OPEN",
        "ASK_CHOICE",
        "CONFIRM",
        "ACK_EMOTION",
        "PRESENCE",
        "INFO_HELP",
        "INSTRUCT",
        "BREATHING",
        "AFFIRM",
        "REDIRECT",
        "REPEAT_PERSIST",
        "BOUNDARY",
        "ASK_SUICIDE",
        "CALL_PSY",
        "HANDOFF",
        "ASK_OTHER",
        "PACE_MATCH",
    }
)
BAD_ACTS = frozenset(
    {
        "CALM_DOWN",
        "DEVALUE",
        "BLAME",
        "RUDE",
        "THREAT_HANGUP",
        "ARGUE",
        "FALSE_PROMISE",
        "FALSE_ADVICE",
        "NEG_PARTICLE",
        "TRIGGER_WORD",
        "JARGON",
    }
)
EVENTS = frozenset({"DEAD_AIR", "REASK_KNOWN", "PERSIST_NO_REASON", "INTERRUPT", "HANGUP_FIRST", "IGNORE_EMOTION"})
ALL_ACTS = GOOD_ACTS | BAD_ACTS | EVENTS
ROLLBACK = frozenset({"RUDE", "THREAT_HANGUP", "REASK_KNOWN"})  # откат к стартовому уровню

ACT_TITLES: dict[str, str] = {
    "GREET": "приветствие по регламенту",
    "NAME_USE": "обращение по имени",
    "ASK_CLOSED": "короткий вопрос по делу",
    "ASK_OPEN": "открытый вопрос",
    "ASK_CHOICE": "вопрос-выбор",
    "CONFIRM": "подтверждение данных (замкнутый контур)",
    "ACK_EMOTION": "признание эмоции",
    "PRESENCE": "«я на линии, я с вами»",
    "INFO_HELP": "правдиво о помощи",
    "INSTRUCT": "короткая инструкция",
    "BREATHING": "дыхание, заземление",
    "AFFIRM": "поддержка действий заявителя",
    "REDIRECT": "признал и вернул к делу",
    "REPEAT_PERSIST": "повторная настойчивость",
    "BOUNDARY": "спокойная граница",
    "ASK_SUICIDE": "прямой вопрос о намерении",
    "CALL_PSY": "подключение психолога",
    "HANDOFF": "«тёплая» передача",
    "ASK_OTHER": "просьба передать трубку",
    "PACE_MATCH": "подстройка темпа",
    "CALM_DOWN": "«успокойтесь», «возьмите себя в руки»",
    "DEVALUE": "обесценивание",
    "BLAME": "упрёк, морализаторство",
    "RUDE": "грубость, сарказм",
    "THREAT_HANGUP": "угроза прекратить разговор",
    "ARGUE": "спор, переубеждение",
    "FALSE_PROMISE": "ложное обещание",
    "FALSE_ADVICE": "вредный совет (вода, пощёчина, трясти)",
    "NEG_PARTICLE": "инструкция с «не»",
    "TRIGGER_WORD": "слова «паника», «ужас», «катастрофа»",
    "JARGON": "служебный жаргон",
    "DEAD_AIR": "долгая пауза",
    "REASK_KNOWN": "переспросил уже сообщённое",
    "PERSIST_NO_REASON": "повтор без обоснования",
    "INTERRUPT": "перебил заявителя",
    "HANGUP_FIRST": "завершил звонок первым",
    "IGNORE_EMOTION": "эмоция осталась без ответа",
}

TOPICS = ("what", "address", "floor", "name", "phone", "victims", "danger", "access", "gas", "status")
# Ремарки — закрытый список: убираются из озвучиваемого текста, показываются курсивом, озвучиваются звуком
REMARKS = (
    "плачет",
    "всхлипывает",
    "кричит",
    "задыхается",
    "тяжело дышит",
    "пауза",
    "шёпотом",
    "смеётся",
    "кладёт трубку",
)
REMARK_SOUND = {
    "плачет": "sob",
    "всхлипывает": "sniff",
    "кричит": "scream",
    "задыхается": "gasp",
    "тяжело дышит": "pant",
    "смеётся": "laugh",
    "пауза": "pause",
    "шёпотом": "whisper",
    "кладёт трубку": "hangup",
}
GROUPS = ("stress_reaction", "crisis", "caller_type")
LEVEL_TITLES = {
    1: "спокоен",
    2: "тревожен, сотрудничает",
    3: "расстроен, сотрудничает",
    4: "не сотрудничает",
    5: "неуправляем",
}


class PsyCatalogError(ValueError):
    """Ошибка в каталоге профилей: приложение не стартует с некорректным каталогом."""


# ------------------------------------------------------------------ профиль


@dataclass(frozen=True)
class Trigger:
    at_s: float
    if_level_ge: int
    delta: int
    note: str = ""


@dataclass(frozen=True)
class Stage:
    id: str
    trust_ge: float | None = None
    act: str | None = None
    any_act: frozenset[str] = frozenset()


@dataclass(frozen=True)
class PsyProfile:
    id: str
    title: str
    group: str
    direction: str  # up — возбуждение, down — торможение (для голоса)
    start: int
    floor: int
    deescalate_cost: int
    coherence: float
    compliance_cap: float
    can_hang_up: bool
    needs_instructions: bool
    deescalates: bool
    sensitive: bool
    pinned_only: bool
    pool: int
    dead_air_s: float
    norm_address_s: float
    key_acts: frozenset[str]
    helps: Mapping[str, float]
    hurts: Mapping[str, float]
    critical: frozenset[str]
    required_routing: tuple[str, ...]
    gates: Mapping[str, int]
    triggers: tuple[Trigger, ...]
    stages: tuple[Stage, ...]
    stage_gates: Mapping[str, str]
    speech: Mapping[int, str]
    offline: Mapping[str, tuple[str, ...]]
    rules: str
    applicant_status: str | None
    nonverbal: tuple[str, ...]
    scene: str | None
    child_voice: bool
    elderly_voice: bool
    sources: tuple[str, ...]

    def snapshot(self) -> dict[str, Any]:
        """Что звонок запоминает о профиле для оценки: правка каталога не меняет прошедшие попытки."""
        return {
            "profile": self.id,
            "title": self.title,
            "group": self.group,
            "sensitive": self.sensitive,
            "start": self.start,
            "floor": self.floor,
            "deescalates": self.deescalates,
            "key_acts": sorted(self.key_acts),
            "critical": sorted(self.critical),
            "required_routing": list(self.required_routing),
            "needs_instructions": self.needs_instructions,
            "norm_address_s": self.norm_address_s,
            "stages": [s.id for s in self.stages],
            "can_hang_up": self.can_hang_up,
            "sources": list(self.sources),
        }


def _acts(values: Sequence[str], where: str) -> frozenset[str]:
    unknown = [v for v in values if v not in ALL_ACTS]
    if unknown:
        raise PsyCatalogError(f"{where}: неизвестные коды действий {unknown}")
    return frozenset(values)


def _weights(values: Mapping[str, Any], where: str) -> dict[str, float]:
    _acts(list(values), where)
    return {k: float(v) for k, v in values.items()}


def parse_profile(pid: str, raw: Mapping[str, Any], defaults: Mapping[str, Any]) -> PsyProfile:
    """Строка каталога → профиль; любая ошибка — PsyCatalogError с указанием профиля и поля."""
    where = f"профиль {pid}"

    def get(key: str, default: Any = None) -> Any:
        return raw.get(key, defaults.get(key, default))

    try:
        start, floor = int(raw["start"]), int(raw["floor"])
    except (KeyError, TypeError, ValueError) as e:
        raise PsyCatalogError(f"{where}: нужны целые start и floor") from e
    if not (1 <= floor <= start <= 5):
        raise PsyCatalogError(f"{where}: должно быть 1 ≤ floor ≤ start ≤ 5")
    if raw.get("group") not in GROUPS:
        raise PsyCatalogError(f"{where}: group — одно из {GROUPS}")
    if raw.get("direction") not in ("up", "down"):
        raise PsyCatalogError(f"{where}: direction — up или down")
    gates = {**defaults.get("gates", {}), **raw.get("gates", {})}
    if set(gates) - set(TOPICS):
        raise PsyCatalogError(f"{where}: ворота для неизвестных тем {sorted(set(gates) - set(TOPICS))}")
    stages = tuple(
        Stage(
            id=str(s["id"]),
            trust_ge=float(s["trust_ge"]) if "trust_ge" in s else None,
            act=s.get("act"),
            any_act=_acts(s.get("any_act", []), f"{where}, этап {s.get('id')}"),
        )
        for s in raw.get("stages", [])
    )
    stage_ids = [s.id for s in stages]
    for s in stages:
        if s.act is not None:
            _acts([s.act], f"{where}, этап {s.id}")
    stage_gates = {str(k): str(v) for k, v in raw.get("stage_gates", {}).items()}
    if set(stage_gates.values()) - set(stage_ids):
        raise PsyCatalogError(f"{where}: stage_gates ссылается на неизвестные этапы")
    offline = {str(k): tuple(str(x) for x in v) for k, v in (raw.get("offline") or {}).items()}
    if "refuse" not in offline or not offline["refuse"]:
        raise PsyCatalogError(f"{where}: нужны offline.refuse — ответы, когда тема закрыта")
    for texts in offline.values():
        for t in texts:
            for remark in _remarks_in(t):
                if remark not in REMARKS:
                    raise PsyCatalogError(f"{where}: ремарка «{remark}» не из закрытого списка")
    voice = raw.get("voice") or {}
    return PsyProfile(
        id=pid,
        title=str(raw.get("title") or pid),
        group=str(raw["group"]),
        direction=str(raw["direction"]),
        start=start,
        floor=floor,
        deescalate_cost=max(1, int(get("deescalate_cost", 2))),
        coherence=float(get("coherence", 0.8)),
        compliance_cap=float(get("compliance_cap", 1.0)),
        can_hang_up=bool(get("can_hang_up", False)),
        needs_instructions=bool(get("needs_instructions", False)),
        deescalates=bool(raw.get("deescalates", True)),
        sensitive=bool(raw.get("sensitive", False)),
        pinned_only=bool(raw.get("pinned_only", False)),
        pool=int(get("pool", 3)),
        dead_air_s=float(get("dead_air_s", 8)),
        norm_address_s=float(get("norm_address_s", 45)),
        key_acts=_acts(raw.get("key_acts", []), f"{where}, key_acts"),
        helps=_weights(raw.get("helps", {}), f"{where}, helps"),
        hurts=_weights(raw.get("hurts", {}), f"{where}, hurts"),
        critical=_acts(raw.get("critical", []), f"{where}, critical"),
        required_routing=tuple(str(x) for x in raw.get("required_routing", [])),
        gates={k: int(v) for k, v in gates.items()},
        triggers=tuple(
            Trigger(
                at_s=float(t["at_s"]), if_level_ge=int(t["if_level_ge"]), delta=int(t["delta"]), note=t.get("note", "")
            )
            for t in raw.get("triggers", [])
        ),
        stages=stages,
        stage_gates=stage_gates,
        speech={int(k): str(v) for k, v in (raw.get("speech") or {}).items()},
        offline=offline,
        rules=str(raw.get("rules") or ""),
        applicant_status=raw.get("applicant_status"),
        nonverbal=tuple(str(x) for x in voice.get("nonverbal", [])),
        scene=voice.get("scene"),
        child_voice=bool(voice.get("child", False)),
        elderly_voice=bool(voice.get("elderly", False)),
        sources=tuple(str(x) for x in raw.get("sources", [])),
    )


def parse_catalog(raw: Mapping[str, Any]) -> tuple[int, dict[str, PsyProfile]]:
    if not isinstance(raw, Mapping) or "profiles" not in raw:
        raise PsyCatalogError("каталог: нет раздела profiles")
    defaults = raw.get("defaults") or {}
    profiles = {str(pid): parse_profile(str(pid), p, defaults) for pid, p in raw["profiles"].items()}
    if not profiles:
        raise PsyCatalogError("каталог пуст")
    return int(raw.get("version", 1)), profiles


def _remarks_in(text: str) -> list[str]:
    out, i = [], 0
    while (a := text.find("[", i)) >= 0 and (b := text.find("]", a)) > a:
        out.append(text[a + 1 : b].strip().lower())
        i = b + 1
    return out


# ------------------------------------------------------------------ состояние


@dataclass
class PsyState:
    level: int
    trust: float = 0.3
    credit: float = 0.0
    stage: str = ""
    peak: int = 0
    turn: int = 0
    bad_streak: int = 0
    hung_up: bool = False
    fired: list[int] = field(default_factory=list)
    confirmed: list[str] = field(default_factory=list)  # темы, которые оператор подтвердил (CONFIRM)
    instructions_followed: int = 0
    persist: int = 0  # повторов подряд одной просьбы

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> PsyState:
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)


@dataclass(frozen=True)
class Delta:
    cause: str  # код действия или «trigger»
    change: int  # изменение уровня: +1, −1
    note: str = ""


def initial_state(p: PsyProfile) -> PsyState:
    return PsyState(level=p.start, peak=p.start, stage=p.stages[0].id if p.stages else "")


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def step(
    p: PsyProfile, state: PsyState, acts: set[str], elapsed_s: float, rng: random.Random
) -> tuple[PsyState, list[Delta]]:
    """Один ход разговора: действия оператора → новое состояние и причины изменения уровня."""
    s = PsyState.from_dict(state.to_dict())
    deltas: list[Delta] = []
    hurt_acts = sorted(a for a in acts if p.hurts.get(a, 0) > 0)
    hurt = sum(p.hurts[a] for a in hurt_acts)
    if hurt > 0:  # эскалация быстрая: одно запрещённое действие — сразу +1
        before = s.level
        s.level = min(5, s.level + min(2, max(1, math.ceil(hurt))))
        if set(hurt_acts) & ROLLBACK:
            s.level = max(s.level, p.start)
        if s.level != before:
            deltas.append(Delta(cause=hurt_acts[0], change=s.level - before, note=", ".join(hurt_acts)))
        s.credit = 0.0
        s.trust = _clamp(s.trust - 0.15 * hurt, 0.0, p.compliance_cap)
        s.bad_streak += 1
    else:
        s.bad_streak = 0
        help_ = sum(p.helps.get(a, 0) for a in acts)
        if help_ > 0:
            s.credit += help_
            s.trust = _clamp(s.trust + 0.08 * help_, 0.0, p.compliance_cap)
        if p.deescalates:
            cost = max(1, p.deescalate_cost + rng.choice((-1, 0, 0, 1)))  # шум: бот не выучивается наизусть
            while s.credit >= cost and s.level > p.floor:
                s.level -= 1
                s.credit -= cost
                best = max((a for a in acts if p.helps.get(a, 0) > 0), key=lambda a: p.helps[a], default="")
                deltas.append(Delta(cause=best, change=-1))
    for i, t in enumerate(p.triggers):  # сценарные события по времени — независимо от оператора
        if i not in s.fired and elapsed_s >= t.at_s and s.level >= t.if_level_ge:
            s.fired.append(i)
            before = s.level
            s.level = int(_clamp(s.level + t.delta, 1, 5))
            deltas.append(Delta(cause="trigger", change=s.level - before, note=t.note))
    if "CONFIRM" in acts:
        s.confirmed = sorted({*s.confirmed, "address"})
    if "INSTRUCT" in acts and s.level <= 3 and s.trust >= 0.3:
        s.instructions_followed += 1
    _advance_stage(p, s, acts)
    s.hung_up = s.hung_up or (p.can_hang_up and s.level == 5 and s.bad_streak >= 3)
    s.peak = max(s.peak, s.level)
    s.turn += 1
    return s, deltas


def _advance_stage(p: PsyProfile, s: PsyState, acts: set[str]) -> None:
    if not p.stages:
        return
    ids = [st.id for st in p.stages]
    i = ids.index(s.stage) if s.stage in ids else 0
    while i + 1 < len(p.stages):
        nxt = p.stages[i + 1]
        ok = (
            (nxt.trust_ge is None or s.trust >= nxt.trust_ge)
            and (nxt.act is None or nxt.act in acts)
            and (not nxt.any_act or bool(nxt.any_act & acts))
        )
        if not ok:
            break
        i += 1
    s.stage = p.stages[i].id


def gates(p: PsyProfile, s: PsyState) -> set[str]:
    """Темы легенды, которые заявитель в этом состоянии может сообщить."""
    ids = [st.id for st in p.stages]
    reached = ids.index(s.stage) if s.stage in ids else len(ids)
    out = {"what"}
    for topic in TOPICS:
        if topic == "what" or p.gates.get(topic, 5) < s.level:
            continue
        need = p.stage_gates.get(topic)
        if need is not None and ids.index(need) > reached:
            continue
        out.add(topic)
    return out


# ------------------------------------------------------------------ голос

_UP = {1: (1.0, 0, 0), 2: (1.05, 1, 0), 3: (1.12, 2, 2), 4: (1.2, 3, 4), 5: (1.3, 4, 6)}
_DOWN = {1: (1.0, 0, 0), 2: (0.95, -1, -1), 3: (0.88, -2, -3), 4: (0.8, -2, -4), 5: (0.75, -3, -6)}


def voice_for(p: PsyProfile, s: PsyState, remarks: Sequence[str], intensity: int = 2) -> dict[str, Any]:
    """Параметры голоса реплики для синтеза (контракт для голосового / дуплекс-адаптера, руководство §7).

    Темп — множитель, тон — полутоны, громкость — дБ. Интенсивность 1–3 масштабирует отклонение от нейтрального."""
    rate, pitch, gain = (_UP if p.direction == "up" else _DOWN)[s.level]
    k = {1: 0.5, 2: 1.0, 3: 1.3}.get(intensity, 1.0)
    sounds = [REMARK_SOUND[r] for r in remarks if r in REMARK_SOUND]
    if s.level >= 4 and not sounds:
        sounds = list(p.nonverbal[:1])
    return {
        "profile": p.id,
        "direction": p.direction,
        "level": s.level,
        "rate": round(1 + (rate - 1) * k, 2),
        "pitch_st": round(pitch * k, 1),
        "gain_db": round(gain * k, 1),
        "nonverbal": sounds,
        "scene": p.scene,
        "voice": "child" if p.child_voice else "elderly" if p.elderly_voice else None,
        "intensity": intensity,
    }


# ------------------------------------------------------------------ выбор профиля

PSY_DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "share": 0.3,  # доля звонков с профилем: реальные звонящие в основном спокойны (средний ECCS 1,05–1,21)
    "profiles": "auto",
    "intensity": 2,
    "weight": 0.0,  # вес блока «Работа с заявителем» в итоге; 0 — показывается рядом, в итог не входит
    "sensitive": [],
    "llm_acts": False,
}


def psy_settings(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    return {**PSY_DEFAULTS, **(dict(raw) if raw else {})}


def choose_profile(
    catalog: Mapping[str, PsyProfile],
    settings: Mapping[str, Any] | None,
    difficulty: int,
    rng: random.Random,
    pinned: str | None = None,
) -> PsyProfile | None:
    """Профиль звонка: закреплённый за сценарием или по жребию из набора занятия (руководство §4.2)."""
    cfg = psy_settings(settings)
    if not cfg["enabled"]:
        return None
    allowed_sensitive = set(cfg["sensitive"] or [])
    if pinned and pinned in catalog:
        p = catalog[pinned]
        return p if not p.sensitive or p.id in allowed_sensitive else None
    if rng.random() >= float(cfg["share"]):
        return None
    chosen = cfg["profiles"]
    if isinstance(chosen, list) and chosen:
        pool = [catalog[i] for i in chosen if i in catalog]
    else:
        pool = [p for p in catalog.values() if not p.pinned_only and p.pool <= max(1, difficulty)]
    pool = sorted(
        (p for p in pool if not p.sensitive or p.id in allowed_sensitive),
        key=lambda p: p.id,
    )
    return rng.choice(pool) if pool else None


def check_settings(settings: Mapping[str, Any], catalog_ids: set[str] | None = None) -> None:
    """Проверка `settings.psy` занятия; ValueError с понятным сообщением."""
    cfg = psy_settings(settings)
    if not 0 <= float(cfg["share"]) <= 1:
        raise ValueError("Доля звонков с профилем — от 0 до 1")
    if int(cfg["intensity"]) not in (1, 2, 3):
        raise ValueError("Интенсивность — 1, 2 или 3")
    if not 0 <= float(cfg["weight"]) <= 1:
        raise ValueError("Вес блока «Работа с заявителем» — от 0 до 1")
    if catalog_ids is not None:
        ids = list(cfg["sensitive"] or [])
        if isinstance(cfg["profiles"], list):
            ids += cfg["profiles"]
        unknown = sorted(set(ids) - catalog_ids)
        if unknown:
            raise ValueError(f"Неизвестные профили: {', '.join(unknown)}")


def call_rng(seed: int, turn: int) -> random.Random:
    """Генератор хода: seed звонка + номер хода — прогон воспроизводим."""
    return random.Random(seed * 1_000_003 + turn)
