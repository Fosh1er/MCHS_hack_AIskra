"""Состояние ИИ-заявителя в разговоре (п. 3.6, этап V1): эмоция, напряжение, доверие, готовность отвечать.

Начальное состояние — из сложности сценария и группы происшествия классификатора. Дальше его меняют реплики
оператора по детерминированным правилам: успокоение и присутствие («я вас слышу», «помощь уже едет») снижают
напряжение, обесценивание и давление («успокойтесь», «быстрее») повышают, вопрос по ещё не выясненной теме
повышает готовность отвечать. Правила работают без модели и объяснимы: у каждого изменения — код причины и
сработавший фрагмент. Модель получает состояние в промпте, но не меняет его (ADR-0011).

От прототипа emotional-stt-tts отличается сознательно: короткий вопрос («Адрес?») не штрафуется — краткость
норма опроса 112; уточнение уже выясненного (подтверждение адреса) тоже; успокоить одной длинной репликой
нельзя — категория правил срабатывает раз на реплику, успокаивающая фраза — раз за звонок.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from aiskra.shared.text import search_key

LOW, HIGH = 0, 10
CALMING_CAP = 6  # на сколько всего успокоение может снизить напряжение за звонок


class Emotion(StrEnum):
    CALM = "calm"
    RELIEF = "relief"
    FEAR = "fear"
    PANIC = "panic"
    SHOCK = "shock"
    IRRITATION = "irritation"


EMOTION_TITLES = {
    Emotion.CALM: "спокойствие",
    Emotion.RELIEF: "облегчение",
    Emotion.FEAR: "страх",
    Emotion.PANIC: "паника",
    Emotion.SHOCK: "шок",
    Emotion.IRRITATION: "раздражение",
}


class Band(StrEnum):
    """Полоса напряжения: по ней окрашивается офлайн-ответ и делится кеш ответов модели."""

    CALM = "calm"  # 0–3
    TENSE = "tense"  # 4–7
    PANIC = "panic"  # 8–10


# Группа происшествия (dict_incident_groups) → эмоция на пике напряжения; остальные группы — страх.
_GROUP_EMOTION: dict[int, Emotion] = {
    **dict.fromkeys((1, 3, 5, 18), Emotion.PANIC),  # пожары, взрывы, обрушения, ребёнок в опасности
    **dict.fromkeys((2, 12, 19), Emotion.SHOCK),  # ДТП, транспорт, смертельный исход
    **dict.fromkeys((14, 16, 20, 21, 23), Emotion.IRRITATION),  # городское хозяйство, дорога, соцпомощь, животные…
}
OFFENSE_GROUP = 15  # нарушение правопорядка: с признаком «правонарушение» заявитель говорит шёпотом
# Сложность сценария 1–5 → (напряжение, доверие, готовность отвечать)
_BY_DIFFICULTY = {1: (2, 7, 8), 2: (4, 6, 7), 3: (6, 5, 6), 4: (8, 4, 5), 5: (9, 3, 4)}

# Фразы оператора (после search_key: нижний регистр, ё→е). Порядок внутри категории — порядок проверки.
CALMING = (
    "я вас слышу",
    "я вас понял",
    "я вас поняла",
    "понимаю вас",
    "я с вами",
    "оставайтесь на линии",
    "не кладите трубку",
    "помощь уже",
    "уже едет",
    "уже едут",
    "уже выехал",
    "уже в пути",
    "бригада направлена",
    "мы вам поможем",
    "мы поможем",
    "вы в безопасности",
    "дышите",
    "все будет хорошо",
    "не волнуйтесь",
)
INVALIDATING = (
    "успокойтесь",
    "не кричите",
    "не орите",
    "что вы орете",
    "не истерите",
    "прекратите истерику",
    "хватит истерить",
    "это неважно",
    "это не важно",
    "замолчите",
    "хватит плакать",
)
PRESSURE = (
    "быстрее",
    "быстро говорите",
    "отвечайте на вопрос",
    "мне некогда",
    "говорите по делу",
    "по существу",
    "не тяните",
)


def _clamp(v: int) -> int:
    return max(LOW, min(HIGH, v))


def incident_group(code: str | None) -> int | None:
    """Группа по коду классификатора: номер группы и шесть цифр («1010101» → 1, «15260000» → 15)."""
    if not code or not code.isdigit() or len(code) <= 6:
        return None
    return int(code[:-6])


@dataclass(frozen=True)
class ToneChange:
    """Что изменило состояние: код причины, сработавший фрагмент реплики и сдвиги шкал."""

    reason: str  # calming | invalidating | pressure | on_topic
    fragment: str
    tension: int = 0
    trust: int = 0
    readiness: int = 0

    def to_json(self) -> dict[str, Any]:
        return {
            "reason": self.reason,
            "fragment": self.fragment,
            "tension": self.tension,
            "trust": self.trust,
            "readiness": self.readiness,
        }

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> ToneChange:
        return cls(
            reason=str(raw.get("reason", "")),
            fragment=str(raw.get("fragment", "")),
            tension=int(raw.get("tension", 0)),
            trust=int(raw.get("trust", 0)),
            readiness=int(raw.get("readiness", 0)),
        )


@dataclass(frozen=True)
class ToneSnapshot:
    """Состояние у конкретной реплики собеседника — то, что видит интерфейс и по чему озвучивается реплика.
    Фактов легенды здесь нет (R3.3-02)."""

    emotion: str
    emotion_title: str
    tension: int
    trust: int
    readiness: int
    band: str
    pace: str  # slow | normal | fast | very_fast
    volume: str  # whisper | low | normal | loud
    breathing: str  # calm | tense | rapid | irregular
    changes: list[ToneChange] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "emotion": self.emotion,
            "emotion_title": self.emotion_title,
            "tension": self.tension,
            "trust": self.trust,
            "readiness": self.readiness,
            "band": self.band,
            "pace": self.pace,
            "volume": self.volume,
            "breathing": self.breathing,
            "changes": [c.to_json() for c in self.changes],
        }

    @classmethod
    def from_json(cls, raw: Any) -> ToneSnapshot | None:
        if not isinstance(raw, dict):
            return None
        try:
            return cls(
                emotion=str(raw["emotion"]),
                emotion_title=str(raw.get("emotion_title", "")),
                tension=int(raw["tension"]),
                trust=int(raw["trust"]),
                readiness=int(raw["readiness"]),
                band=str(raw.get("band", "")),
                pace=str(raw.get("pace", "normal")),
                volume=str(raw.get("volume", "normal")),
                breathing=str(raw.get("breathing", "calm")),
                changes=[ToneChange.from_json(c) for c in raw.get("changes", []) if isinstance(c, dict)],
            )
        except (KeyError, TypeError, ValueError):
            return None


@dataclass(kw_only=True)
class CallerTone:
    """Состояние заявителя за звонком. `base` — эмоция сценария на пике; текущая эмоция выводится из напряжения."""

    base: Emotion
    tension: int
    trust: int
    readiness: int
    whisper: bool = False
    calmed: int = 0  # на сколько уже снизило напряжение успокоение (не больше CALMING_CAP)
    used: list[str] = field(default_factory=list)  # успокаивающие фразы, уже засчитанные в этом звонке

    @property
    def emotion(self) -> Emotion:
        if self.tension <= 3:
            return Emotion.RELIEF if self.calmed else Emotion.CALM
        if self.tension <= 7 and self.base is Emotion.PANIC:
            return Emotion.FEAR
        return self.base

    @property
    def band(self) -> Band:
        return Band.CALM if self.tension <= 3 else Band.TENSE if self.tension <= 7 else Band.PANIC

    def delivery(self) -> tuple[str, str, str]:
        """(темп, громкость, дыхание) — производные напряжения: хранить их отдельно незачем."""
        if self.tension <= 3:
            pace, volume, breathing = "slow", "low", "calm"
        elif self.tension <= 5:
            pace, volume, breathing = "normal", "normal", "tense"
        elif self.tension <= 7:
            pace, volume, breathing = "fast", "loud", "rapid"
        else:
            pace, volume, breathing = "very_fast", "loud", "irregular"
        if self.whisper and self.tension >= 4:
            volume = "whisper"
        return pace, volume, breathing

    def snapshot(self, changes: list[ToneChange] | None = None) -> ToneSnapshot:
        pace, volume, breathing = self.delivery()
        return ToneSnapshot(
            emotion=self.emotion.value,
            emotion_title=EMOTION_TITLES[self.emotion],
            tension=self.tension,
            trust=self.trust,
            readiness=self.readiness,
            band=self.band.value,
            pace=pace,
            volume=volume,
            breathing=breathing,
            changes=list(changes or []),
        )

    def react(self, text: str, *, topic: str | None, revealed: list[str]) -> list[ToneChange]:
        """Реплика оператора меняет состояние. Возвращает сработавшие правила — по одному на категорию."""
        key = search_key(text)
        changes: list[ToneChange] = []
        calming = next((p for p in CALMING if p in key and p not in self.used), None)
        if calming:
            drop = min(2, CALMING_CAP - self.calmed)
            self.used.append(calming)
            self.calmed += drop
            changes.append(ToneChange("calming", calming, tension=-drop, trust=2, readiness=1))
        invalidating = next((p for p in INVALIDATING if p in key), None)
        if invalidating:
            changes.append(ToneChange("invalidating", invalidating, tension=2, trust=-2, readiness=-2))
        pressure = next((p for p in PRESSURE if p in key), None)
        if pressure:
            changes.append(ToneChange("pressure", pressure, tension=1, trust=-1, readiness=-1))
        if topic and topic not in revealed:
            changes.append(ToneChange("on_topic", topic, readiness=1))
        for c in changes:
            self.tension = _clamp(self.tension + c.tension)
            self.trust = _clamp(self.trust + c.trust)
            self.readiness = _clamp(self.readiness + c.readiness)
        return changes

    def to_json(self) -> dict[str, Any]:
        return {
            "base": self.base.value,
            "tension": self.tension,
            "trust": self.trust,
            "readiness": self.readiness,
            "whisper": self.whisper,
            "calmed": self.calmed,
            "used": list(self.used),
        }

    @classmethod
    def from_json(cls, raw: Any) -> CallerTone | None:
        """Из поля БД; пустое или повреждённое значение — состояния нет (его создадут заново)."""
        if not isinstance(raw, dict):
            return None
        try:
            return cls(
                base=Emotion(raw["base"]),
                tension=_clamp(int(raw["tension"])),
                trust=_clamp(int(raw["trust"])),
                readiness=_clamp(int(raw["readiness"])),
                whisper=bool(raw.get("whisper", False)),
                calmed=int(raw.get("calmed", 0)),
                used=[str(u) for u in raw.get("used", [])],
            )
        except (KeyError, TypeError, ValueError):
            return None


def initial_tone(difficulty: int | None, group: int | None, *, whisper: bool = False) -> CallerTone:
    """Начальное состояние: числа — по сложности 1–5 (нет сложности — спокойный), эмоция — по группе."""
    tension, trust, readiness = _BY_DIFFICULTY[min(max(difficulty or 1, 1), 5)]
    base = _GROUP_EMOTION.get(group or 0, Emotion.FEAR)
    return CallerTone(base=base, tension=tension, trust=trust, readiness=readiness, whisper=whisper)


def tone_for_legend(legend: dict[str, Any], incident_code: str | None) -> CallerTone:
    """Состояние по легенде сценария. Карточка без сценария (звонок из ДДС) — сложности нет, заявитель спокоен."""
    group = incident_group(incident_code)
    facts = legend.get("facts") or {}
    whisper = group == OFFENSE_GROUP and isinstance(facts, dict) and "offense" in facts
    raw = legend.get("difficulty")
    difficulty = raw if isinstance(raw, int) else None
    return initial_tone(difficulty, group, whisper=whisper)


# Окраска офлайн-ответа по полосе напряжения. Добавляются только слова вокруг ответа — факты легенды не меняются.
_PANIC_OPENERS = ("Скорее! ", "Господи… ", "Алло, вы слышите?! ")
_TENSE_OPENERS = ("Так… ", "Сейчас, сейчас… ", "")
_URGE = re.compile(r"скорее|быстр|помогите", re.IGNORECASE)


def color_reply(text: str, tone: CallerTone, n: int) -> str:
    """Офлайн-ответ голосом человека в этом состоянии; `n` — номер реплики (детерминированный выбор)."""
    band = tone.band
    if band is Band.PANIC:
        if _URGE.search(text):
            return text
        tail = " Быстрее, пожалуйста!" if n % 2 == 0 else ""
        return f"{_PANIC_OPENERS[n % len(_PANIC_OPENERS)]}{text}{tail}"
    if band is Band.TENSE:
        return f"{_TENSE_OPENERS[n % len(_TENSE_OPENERS)]}{text}"
    if tone.emotion is Emotion.RELIEF and n % 2 == 0:
        return f"Да, хорошо. {text}"
    return text


# Подача для серверного синтеза (п. 3.6, V2; спецификация — таблицы 7.3 и 7.4). Стиль — по-английски: так его
# понимают модели с инструкциями (Gemini, OpenAI TTS); модели без инструкций (Piper) получают только темп.
SPEED = {"slow": 0.9, "normal": 1.0, "fast": 1.15, "very_fast": 1.3}
_STYLE_EMOTION = {
    "calm": "a calm",
    "relief": "a relieved, grateful",
    "fear": "a frightened",
    "panic": "a panicking",
    "shock": "a shocked, stunned",
    "irritation": "an irritated",
}
_STYLE_PACE = {"slow": "slow", "normal": "steady", "fast": "fast", "very_fast": "very fast, rushed"}
_STYLE_VOLUME = {"whisper": "whispering", "low": "quiet", "normal": "", "loud": "loud"}
_STYLE_BREATH = {"calm": "", "tense": "tense", "rapid": "breathless", "irregular": "gasping, voice breaking"}
STAFF_STYLE = "a calm, professional emergency service officer, steady and clear"  # старший группы, служба


def speech_style(tone: ToneSnapshot) -> str:
    """«a panicking caller to the 112 emergency line: very fast, rushed, loud, gasping, voice breaking»."""
    parts = [_STYLE_PACE.get(tone.pace, ""), _STYLE_VOLUME.get(tone.volume, ""), _STYLE_BREATH.get(tone.breathing, "")]
    who = _STYLE_EMOTION.get(tone.emotion, "a worried")
    return f"{who} caller to the 112 emergency line: " + ", ".join(p for p in parts if p)


def speech_speed(tone: ToneSnapshot) -> float:
    return SPEED.get(tone.pace, 1.0)
