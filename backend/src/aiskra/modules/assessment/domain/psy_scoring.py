"""Блок оценки «Работа с заявителем» (п. 3.7, ADR-0012): как оператор справился с заявителем в стрессе.

Отдельный от балла 112 и ДДС блок. По умолчанию он показывается рядом и в итог не входит; с весом из настроек
занятия — входит. Критерии и формулы — docs/research/psychology/05_Навыки_оператора_и_оценка.md §4, основания:
- профстандарт 12.002 (приказ Минтруда № 681н): оценивать и учитывать психологическое состояние заявителя,
  ТФ C/04.6 — аудиоконтроль адекватности речевого взаимодействия состоянию заявителя;
- пособия ЦЭПП МЧС 2012 и 2023, пособие Минздрава «Первая помощь» 2025 — приёмы и недопустимые действия;
- шкала ECCS IAED (Clawson & Sinclair 2001) — уровень заявителя; оценка по изменению состояния от начала к концу
  звонка — Kalafat, Gould 2007; CCORS;
- APCO/NENA ANS 1.107.2-2025 (Telephone Protocol/Skills) — контроль звонка, спокойствие, «мёртвое время».

Коды действий оператора приходят готовыми из разметки звонка (модуль training, `meta` реплик), поэтому оценка
воспроизводима и не зависит от модели. ИИ-судья — отдельный критерий, без модели «не проверено».
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from aiskra.modules.assessment.domain.scoring import Criterion, Result, finish, timing_score

PSY_THRESHOLD = 70
WEIGHTS_PSY: dict[str, float] = {
    "psy_contact": 1,
    "psy_critical_info": 2,
    "psy_emotion": 2,
    "psy_techniques": 2,
    "psy_forbidden": 3,
    "psy_speech": 0.5,
    "psy_instructions": 1,
    "psy_routing": 2,
    "psy_outcome": 2,
    "psy_judge": 1,
    "psy_voice": 1,
}
SUPPORT = frozenset({"ACK_EMOTION", "PRESENCE", "INFO_HELP", "BREATHING", "AFFIRM", "NAME_USE"})
ACTION = frozenset({"INSTRUCT", "ASK_CLOSED", "ASK_CHOICE", "REDIRECT", "REPEAT_PERSIST", "BREATHING", "CONFIRM"})
BAD = frozenset(
    {
        "CALM_DOWN",
        "DEVALUE",
        "BLAME",
        "RUDE",
        "THREAT_HANGUP",
        "ARGUE",
        "FALSE_PROMISE",
        "FALSE_ADVICE",
        "REASK_KNOWN",
        "PERSIST_NO_REASON",
    }
)
SPEECH_BAD = frozenset({"NEG_PARTICLE", "TRIGGER_WORD", "JARGON"})
TIMING_BAD = frozenset({"DEAD_AIR", "INTERRUPT"})
MAX_WORDS = 15
# Почему действие — ошибка: короткое объяснение с источником (показывается обучающемуся)
WHY: dict[str, str] = {
    "CALM_DOWN": "пустой призыв «успокойтесь» не помогает и усиливает реакцию (ЦЭПП МЧС, 2023; Минздрав, 2025)",
    "DEVALUE": "обесценивание переживаний недопустимо (ЦЭПП МЧС, 2023; ППП ВОЗ)",
    "BLAME": "упрёки и морализаторство разрушают контакт (ЦЭПП МЧС; Mishara, 2007)",
    "RUDE": "ответная грубость — «атака на лицо» заявителя, звонок срывается (APCO/NENA 1.107.2; Tracy & Tracy, 1998)",
    "THREAT_HANGUP": "угроза прекратить разговор недопустима (Mishara, 2007; профстандарт 12.002)",
    "ARGUE": "спорить и переубеждать нельзя, особенно при бреде (ЦЭПП МЧС, Южный филиал)",
    "FALSE_PROMISE": "нельзя обещать то, что от оператора не зависит (ППП ВОЗ; ЦЭПП МЧС, 2023)",
    "FALSE_ADVICE": "вода в лицо, пощёчина, тряска прямо запрещены (ЦЭПП МЧС 2012, 2023; Минздрав, 2025)",
    "REASK_KNOWN": "переспрашивание уже подтверждённого — признак, что оператор не слушает (APCO/NENA 1.107.2)",
    "PERSIST_NO_REASON": "повтор просьбы без обоснования звучит как неуверенность (IAED; APCO ANS 3.103.3 п. 7.2.1)",
    "NEG_PARTICLE": "инструкции — в побудительном наклонении, без частицы «не» (Минздрав «Первая помощь», 2025)",
    "TRIGGER_WORD": "не употреблять слова «паника», «ужас», «катастрофа» (Минздрав «Первая помощь», 2025)",
    "JARGON": "служебные коды и канцелярит заявителю непонятны (APCO ANS 3.103.3 п. 7.1.2)",
    "DEAD_AIR": "долгая пауза без обратной связи усиливает страх (APCO/NENA 1.107.2 «No dead time»; ЦЭПП)",
    "INTERRUPT": "перебивать — только по необходимости и вежливо (APCO/NENA 1.107.2)",
    "HANGUP_FIRST": "оператор не кладёт трубку первым при кризисе (NENA-STA-001; ЦЭПП МЧС)",
}
ACT_TITLES_SHORT: dict[str, str] = {
    "GREET": "приветствие по регламенту",
    "NAME_USE": "обращение по имени",
    "PRESENCE": "«я на линии, я с вами»",
    "INFO_HELP": "сообщить, что помощь направлена",
    "BREATHING": "дыхание, счёт, заземление",
    "REPEAT_PERSIST": "повторная настойчивость с обоснованием",
    "ACK_EMOTION": "признать эмоцию",
    "REDIRECT": "признать сказанное и вернуть к делу",
    "ASK_CHOICE": "вопрос-выбор",
    "ASK_OPEN": "открытый вопрос",
    "ASK_CLOSED": "короткие вопросы по одному",
    "INSTRUCT": "короткие инструкции",
    "AFFIRM": "поддержать действия заявителя",
    "CONFIRM": "повторить адрес для подтверждения",
    "BOUNDARY": "спокойно обозначить рамки",
    "ASK_SUICIDE": "прямо спросить о намерении",
    "CALL_PSY": "подключить психолога",
    "HANDOFF": "«тёплая» передача: объяснить и остаться на линии",
    "ASK_OTHER": "попросить передать трубку человеку рядом",
}


@dataclass(frozen=True)
class PsyTurn:
    speaker: str  # operator | party | system
    text: str
    at_s: float  # секунд от ответа на звонок
    acts: tuple[str, ...] = ()
    quotes: dict[str, str] = field(default_factory=dict)
    level_before: int | None = None
    level_after: int | None = None
    level: int | None = None  # уровень заявителя после его реплики
    emotional: bool = False
    remarks: tuple[str, ...] = ()
    topic: str | None = None
    blocked: str | None = None
    has_signals: bool = False


@dataclass(frozen=True)
class PsyAttempt:
    profile: dict[str, Any]  # снимок профиля из звонка (training_calls.psy)
    turns: list[PsyTurn]
    ended_by: str | None
    services: list[str]
    call_id: str = ""


def _operator(turns: Sequence[PsyTurn]) -> list[PsyTurn]:
    return [t for t in turns if t.speaker == "operator"]


def _quote(t: PsyTurn, code: str) -> str:
    return (t.quotes.get(code) or t.text)[:80]


def hangup_first(a: PsyAttempt) -> bool:
    """Оператор завершил звонок, когда заявителя нельзя было оставлять: кризис не разрешён или адреса нет."""
    if a.ended_by != "operator" or a.profile.get("paused"):
        return False
    state = a.profile.get("state") or {}
    stages = a.profile.get("stages") or []
    if stages and state.get("stage") != stages[-1]:
        return True
    got_address = any(t.topic == "address" and not t.blocked for t in a.turns if t.speaker == "party")
    return int(state.get("level") or 1) >= 4 and not got_address


def _address_time(a: PsyAttempt) -> tuple[float | None, bool]:
    """Когда получен адрес и подтверждён ли он оператором (замкнутый контур)."""
    confirmed = next((t.at_s for t in _operator(a.turns) if "CONFIRM" in t.acts), None)
    if confirmed is not None:
        return confirmed, True
    got = next((t.at_s for t in a.turns if t.speaker == "party" and t.topic == "address" and not t.blocked), None)
    return got, False


def assess_psy(a: PsyAttempt, *, judge: Criterion | None = None, threshold: float = PSY_THRESHOLD) -> Result:
    p = a.profile
    ops = _operator(a.turns)
    state = p.get("state") or {}
    criteria: list[Criterion] = []

    # К1 контакт
    c = Criterion("psy_contact", 0.0)
    greeted = bool(ops) and "GREET" in ops[0].acts
    name_known = any(t.topic == "name" and not t.blocked for t in a.turns if t.speaker == "party")
    named = any("NAME_USE" in t.acts for t in ops)
    c.score = (0.5 * greeted + 0.5 * named) if name_known else float(greeted)
    if not greeted:
        c.errors.append("Нет приветствия по регламенту в первой реплике («Служба 112, …»)")
    if name_known and not named:
        c.errors.append(
            "Имя заявителя известно, но оператор ни разу не обратился по имени (ЦЭПП МЧС: называть по имени)"
        )
    criteria.append(c)

    # К3 данные под стрессом
    norm = float(p.get("norm_address_s") or 45)
    at, confirmed = _address_time(a)
    c = Criterion("psy_critical_info", 0.0)
    if at is None:
        c.errors.append("Адрес у заявителя так и не получен")
    else:
        c.score = 0.5 * confirmed + 0.5 * timing_score(at, norm) + (0 if confirmed else 0.25)
        c.score = min(1.0, c.score)
        if not confirmed:
            c.errors.append("Адрес не подтверждён повтором (замкнутый контур: NENA-STA-020.1, Lindström 2014)")
        if at > norm:
            c.errors.append(f"Адрес получен на {at:.0f} с при нормативе профиля {norm:.0f} с")
    c.note = f"адрес на {at:.0f} с" if at is not None else ""
    criteria.append(c)

    # К4 ответ на эмоцию — шкала 0/0,5/1 по мотивам ECCS Bylund & Makoul
    scores: list[float] = []
    c = Criterion("psy_emotion", None)
    turns = a.turns
    for i, t in enumerate(turns):
        if t.speaker != "party" or not t.emotional:
            continue
        nxt = next((x for x in turns[i + 1 :] if x.speaker == "operator"), None)
        if nxt is None:
            continue
        acts = set(nxt.acts)
        if acts & BAD:
            scores.append(0.0)
            c.errors.append(f"На эмоцию заявителя — «{nxt.text[:60]}»: ответ с недопустимым действием")
        elif (acts & SUPPORT and acts & ACTION) or ("REPEAT_PERSIST" in acts and (t.level or 0) >= 4):
            scores.append(1.0)
        elif acts & (SUPPORT | ACTION):
            scores.append(0.5)
        else:
            scores.append(0.0)
            c.errors.append(f"Эмоция заявителя осталась без ответа: «{nxt.text[:60]}»")
    if scores:
        c.score = round(sum(scores) / len(scores), 3)
        c.note = f"эмоциональных реплик заявителя: {len(scores)}"
    else:
        c.note = "эмоциональных реплик не было"
    criteria.append(c)

    # К5 приёмы профиля
    key = [k for k in p.get("key_acts") or []]
    used = {x for t in ops for x in t.acts}
    c = Criterion("psy_techniques", None)
    if key:
        hit = [k for k in key if k in used]
        c.score = round(len(hit) / len(key), 3)
        missed = [ACT_TITLES_SHORT.get(k, k) for k in key if k not in used]
        if missed:
            c.errors.append(f"Для состояния «{p.get('title')}» не применено: " + "; ".join(missed))
    criteria.append(c)

    # К6 недопустимые действия
    c = Criterion("psy_forbidden", 1.0)
    critical = set(p.get("critical") or [])
    count = 0
    for t in ops:
        for code in t.acts:
            if code in BAD:
                count += 1
                c.errors.append(f"«{_quote(t, code)}» — {WHY.get(code, code)}")
                c.critical = c.critical or code in critical
    if hangup_first(a):
        count += 1
        c.errors.append(WHY["HANGUP_FIRST"])
        c.critical = c.critical or "HANGUP_FIRST" in critical
    c.score = max(0.0, 1 - 0.25 * count)
    criteria.append(c)

    # К7 речевой стандарт
    c = Criterion("psy_speech", None)
    if ops:
        ok = 0
        for t in ops:
            bad = set(t.acts) & SPEECH_BAD
            long = len(t.text.split()) > MAX_WORDS and "HANDOFF" not in t.acts
            if bad:
                for code in sorted(bad):
                    c.errors.append(f"«{_quote(t, code)}» — {WHY[code]}")
            if long:
                c.errors.append(
                    f"Длинная реплика ({len(t.text.split())} слов): в стрессе нужны короткие фразы (Минздрав, 2025)"
                )
            ok += not bad and not long
        c.score = round(ok / len(ops), 3)
    criteria.append(c)

    # К8 инструкции
    c = Criterion("psy_instructions", None)
    if p.get("needs_instructions"):
        gave = any("INSTRUCT" in t.acts or "BREATHING" in t.acts for t in ops)
        followed = int(state.get("instructions_followed") or 0) > 0
        c.score = 0.5 * gave + 0.5 * followed
        if not gave:
            c.errors.append("Заявителю не дано ни одной короткой инструкции безопасности")
        elif not followed:
            c.errors.append("Инструкция дана, пока заявитель был не в состоянии её выполнить — сначала снизьте уровень")
    criteria.append(c)

    # К9 маршрутизация
    c = Criterion("psy_routing", None)
    routing = list(p.get("required_routing") or [])
    if routing:
        done = 0
        for r in routing:
            if r == "psy":
                ok = "CALL_PSY" in used or "HANDOFF" in used
                if not ok:
                    c.errors.append("Не подключён психолог (МР МЧС по обучению персонала 112; оператор-психолог ЦОВ)")
                    c.critical = c.critical or bool(p.get("sensitive"))
            elif r.startswith("service:"):
                codes = r.split(":", 1)[1].split("|")
                ok = any(s in a.services for s in codes)
                if not ok:
                    c.errors.append(f"В карточке нет службы {codes[0]}: состояние требует медицинской помощи")
            else:
                ok = True
            done += ok
        c.score = round(done / len(routing), 3)
    criteria.append(c)

    # К11 исход — изменение состояния от начала к концу звонка (Kalafat, Gould 2007; CCORS)
    c = Criterion("psy_outcome", None)
    start, floor = int(p.get("start") or 3), int(p.get("floor") or 1)
    final, peak = int(state.get("level") or start), int(state.get("peak") or start)
    hung_up = bool(state.get("hung_up"))
    if p.get("deescalates", True):
        span = max(1, start - floor)
        c.score = round(
            0.5 * max(0.0, min(1.0, (start - final) / span)) + 0.3 * (peak <= start) + 0.2 * (not hung_up), 3
        )
        if final >= start:
            c.errors.append(f"Состояние заявителя не улучшилось: уровень {start} → {final} по шкале ECCS")
        if peak > start:
            c.errors.append(f"Заявитель доведён до уровня {peak} — выше исходного {start}")
        if hung_up:
            c.errors.append("Заявитель положил трубку: контакт потерян")
        c.note = f"уровень ECCS {start} → {final}, пик {peak}"
    else:
        c.note = "для этого состояния оценивается решение, а не успокоение"
    criteria.append(c)

    # ИИ-судья
    criteria.append(judge or Criterion("psy_judge", None, note="не проверено: ИИ-судья не подключён"))

    # К10 спокойствие в голосе — только при голосовом канале
    c = Criterion("psy_voice", None, note="нет голосового канала: задержки и перебивания не измерялись")
    if any(t.has_signals for t in ops):
        n = 0
        for t in ops:
            for code in set(t.acts) & TIMING_BAD:
                n += 1
                c.errors.append(f"{WHY[code]}")
        c.score = max(0.0, 1 - 0.25 * n)
        c.note = ""
    criteria.append(c)

    stats = {
        "profile": p.get("profile"),
        "title": p.get("title"),
        "start": start,
        "final": final,
        "peak": peak,
        "hung_up": hung_up,
        "time_to_address_s": at,
        "address_confirmed": confirmed,
        "hangup_first": hangup_first(a),
        "sources": list(p.get("sources") or []),
    }
    return finish("psy", criteria, WEIGHTS_PSY, True, threshold, stats)


def timeline(a: PsyAttempt) -> list[dict[str, Any]]:
    """Лента разбора: реплика → действия оператора → уровень заявителя (формат SimPatient / PEARLS)."""
    good = {"GREET"} | SUPPORT | ACTION | {"ASK_OPEN", "BOUNDARY", "ASK_SUICIDE", "CALL_PSY", "HANDOFF", "ASK_OTHER"}
    out = []
    for t in a.turns:
        item: dict[str, Any] = {"at_s": round(t.at_s, 1), "speaker": t.speaker, "text": t.text}
        if t.speaker == "operator":
            item["acts"] = [
                {
                    "code": code,
                    "good": code in good,
                    "why": WHY.get(code, ""),
                    "title": ACT_TITLES_SHORT.get(code) or WHY.get(code, code).split(" (")[0],
                }
                for code in t.acts
            ]
            item["level_before"], item["level_after"] = t.level_before, t.level_after
        else:
            item["remarks"] = list(t.remarks)
            item["level"] = t.level
            item["blocked"] = t.blocked
        out.append(item)
    return out
