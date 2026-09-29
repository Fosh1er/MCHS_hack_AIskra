"""Психологический модификатор (п. 3.6): каталог, движок состояния, классификатор действий, реплики, валидатор,
блок оценки «Работа с заявителем» и бенчмарк мутаций (по образцу п. 3.5)."""

from __future__ import annotations

import asyncio
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from aiskra.ai.adapters.fake import FakeLLM
from aiskra.ai.router import ModelRouter, TaskProfile
from aiskra.ai.tasks import AITask
from aiskra.modules.assessment.domain.psy_scoring import PsyAttempt, PsyTurn, assess_psy
from aiskra.modules.training.application.actors import Actors
from aiskra.modules.training.application.psy import PsyDirector, TurnSignals, start_psy
from aiskra.modules.training.domain.actors import applicant_reply
from aiskra.modules.training.domain.call import CallMessage, Speaker
from aiskra.modules.training.domain.psy import (
    PsyCatalogError,
    call_rng,
    check_settings,
    choose_profile,
    gates,
    initial_state,
    parse_catalog,
    step,
    voice_for,
)
from aiskra.modules.training.domain.psy_acts import ActContext, classify_offline, codes
from aiskra.modules.training.domain.psy_render import parse_remarks, validate
from aiskra.modules.training.domain.scenario import AddressFacts, IncidentFacts, ServiceFacts, build_scenario
from aiskra.modules.training.infrastructure.psy_catalog import YamlPsyCatalog

CATALOG_PATH = Path(__file__).resolve().parents[3] / "data" / "dictionaries" / "psy_profiles.yaml"
CATALOG = YamlPsyCatalog(CATALOG_PATH)
FIRE = IncidentFacts(
    code="1010101",
    group_id=1,
    group_title="Пожары",
    card_type="101",
    card_type_title="101",
    sign1="в жилом доме",
    sign2="квартира",
    sign3="открытое пламя",
    final_type="пожар: квартира",
    flags=["victims"],
)
ADDR = AddressFacts("Тверская улица", "7", "", "", "tverskoy", "Тверской", "CAO", 55.76, 37.61)
LEGEND = build_scenario(
    incident=FIRE,
    address=ADDR,
    services=[ServiceFacts("S101", "Служба 101", True, "")],
    story={"description": "Горит квартира, дым на лестнице", "opening": "Алло! У нас пожар!", "details": ""},
    flags=["victims"],
    difficulty=4,
    rng=random.Random(3),
    source="test",
    author_id=None,
).legend


def acts(text: str, **ctx: Any) -> set[str]:
    return codes(classify_offline(text, ActContext(**ctx)))


# ------------------------------------------------------------------ каталог


def test_catalog_loads_and_is_grounded_in_sources() -> None:
    profiles = CATALOG.profiles()
    assert {"panic", "crying", "hysteria", "aggression", "apathy", "stupor", "suicidal", "child"} <= set(profiles)
    for p in profiles.values():
        assert p.sources, f"у профиля {p.id} нет ссылок на источники"
        assert p.offline["refuse"], p.id
        assert 1 <= p.floor <= p.start <= 5
    assert profiles["suicidal"].sensitive and profiles["suicidal"].pinned_only
    assert "FALSE_ADVICE" in profiles["hysteria"].critical  # вода, пощёчина — ЦЭПП запрещает


def test_catalog_rejects_unknown_act_and_remark() -> None:
    base = {"group": "stress_reaction", "direction": "up", "start": 3, "floor": 1, "offline": {"refuse": ["нет"]}}
    with pytest.raises(PsyCatalogError, match="неизвестные коды"):
        parse_catalog({"profiles": {"x": {**base, "helps": {"HUG": 1}}}})
    with pytest.raises(PsyCatalogError, match="ремарка"):
        parse_catalog({"profiles": {"x": {**base, "offline": {"refuse": ["[танцует] нет"]}}}})
    with pytest.raises(PsyCatalogError, match="floor"):
        parse_catalog({"profiles": {"x": {**base, "start": 1, "floor": 3}}})


# ------------------------------------------------------------------ классификатор


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Служба 112, что у вас случилось?", {"GREET", "ASK_OPEN"}),
        ("Успокойтесь! Назовите адрес.", {"CALM_DOWN", "ASK_CLOSED"}),
        ("Возьмите себя в руки", {"CALM_DOWN"}),
        ("Я на линии, помощь уже направлена", {"PRESENCE", "INFO_HELP"}),
        ("Понимаю, вам страшно. Какой адрес?", {"ACK_EMOTION", "ASK_CLOSED"}),
        ("Выйдите из квартиры и закройте дверь", {"INSTRUCT"}),
        ("Дышите со мной: вдох… выдох", {"BREATHING"}),
        ("Если будете кричать — положу трубку", {"THREAT_HANGUP"}),
        ("Плесните ей водой в лицо", {"FALSE_ADVICE"}),
        ("Вы думаете о том, чтобы покончить с собой?", {"ASK_SUICIDE"}),
        ("Сейчас подключаю психолога, я останусь на линии", {"CALL_PSY", "HANDOFF"}),
        ("Вы что, глухой?", {"RUDE"}),
        ("Всё будет хорошо, через минуту будут", {"FALSE_PROMISE"}),
        ("Это не так, никто за вами не следит", {"ARGUE"}),
        ("Не бегите!", {"NEG_PARTICLE"}),
        ("Что сейчас важнее: адрес или состояние человека?", {"ASK_CHOICE"}),
        ("Вы всё делаете правильно", {"AFFIRM"}),
    ],
)
def test_classifier_finds_acts(text: str, expected: set[str]) -> None:
    assert expected <= acts(text, first_turn=text.startswith("Служба"))


def test_classifier_exceptions_do_not_fire() -> None:
    assert "CALM_DOWN" not in acts("Не беспокойтесь, я с вами")  # «не беспокойтесь» — не «успокойтесь»
    assert "NEG_PARTICLE" not in acts("Не кладите трубку, я на линии")  # удержание на линии — норма
    assert "INSTRUCT" not in acts("Здравствуйте")
    assert "GREET" not in acts("Служба 112", first_turn=False)


def test_name_confirm_and_repeat() -> None:
    assert "NAME_USE" in acts("Анна, назовите адрес", applicant_first_name="Анна")
    confirm = acts("Тверская, дом 7, верно?", address_tokens=("тверская", "7"))
    assert "CONFIRM" in confirm
    q = "Назовите адрес, мне нужен адрес, чтобы направить помощь"
    assert "REPEAT_PERSIST" in acts(q, previous_operator=(q,))  # та же просьба теми же словами (IAED)
    assert "REASK_KNOWN" in acts("Какой адрес?", confirmed=frozenset({"address"}))
    assert "PERSIST_NO_REASON" in acts("Адрес назовите", previous_operator=("Адрес назовите",), persist_run=3)


# ------------------------------------------------------------------ движок


def test_escalation_is_fast_deescalation_is_slow() -> None:
    p = CATALOG.get("panic")
    assert p is not None
    s = initial_state(p)
    s, d = step(p, s, {"CALM_DOWN"}, 5, call_rng(1, 1))
    assert s.level == 5 and d[0].cause == "CALM_DOWN"  # одно «успокойтесь» — сразу +1
    assert gates(p, s) == {"what"}  # в панике адрес не назвать
    s, d = step(p, s, {"ASK_CLOSED"}, 10, call_rng(1, 2))
    assert s.level == 5  # одного короткого вопроса мало
    for turn in range(3, 8):
        s, _ = step(p, s, {"PRESENCE", "REPEAT_PERSIST"}, 10 + turn, call_rng(1, turn))
    assert s.level <= 3 and "address" in gates(p, s)


def test_rollback_floor_triggers_and_determinism() -> None:
    p = CATALOG.get("aggression")
    assert p is not None
    s = initial_state(p)
    for turn in range(1, 12):
        s, _ = step(p, s, {"NAME_USE", "ASK_CHOICE", "ACK_EMOTION"}, turn, call_rng(7, turn))
    assert s.level == p.floor  # агрессор не станет «спокойным и благодарным»
    s2, _ = step(p, s, {"RUDE"}, 30, call_rng(7, 12))
    assert s2.level >= p.start  # ответная грубость — откат к старту
    panic = CATALOG.get("panic")
    assert panic is not None
    t = initial_state(panic)
    t, d = step(panic, t, set(), 95, call_rng(1, 1))
    assert any(x.cause == "trigger" for x in d)  # обстановка ухудшилась по времени

    def run(seed: int) -> list[int]:
        st, levels = initial_state(panic), []
        for turn in range(1, 8):
            st, _ = step(panic, st, {"PRESENCE"}, turn, call_rng(seed, turn))
            levels.append(st.level)
        return levels

    assert run(5) == run(5)  # воспроизводимость: seed → та же траектория


def test_suicidal_stages_open_location_only_after_contact() -> None:
    p = CATALOG.get("suicidal")
    assert p is not None
    s = initial_state(p)
    assert "address" not in gates(p, s)
    s, _ = step(p, s, {"PRESENCE", "ACK_EMOTION"}, 5, call_rng(2, 1))
    s, _ = step(p, s, {"ASK_SUICIDE", "PRESENCE"}, 10, call_rng(2, 2))
    assert s.stage in {"plan_disclosed", "location_disclosed"}
    for turn in range(3, 7):
        s, _ = step(p, s, {"PRESENCE", "ACK_EMOTION"}, 10 + turn, call_rng(2, turn))
    assert "address" in gates(p, s)
    s, _ = step(p, s, {"CALL_PSY", "HANDOFF"}, 40, call_rng(2, 9))
    assert s.stage == "agreed_to_wait"


def test_voice_contract() -> None:
    p = CATALOG.get("crying")
    assert p is not None
    v = voice_for(p, initial_state(p), ["плачет"], intensity=2)
    assert v["direction"] == "down" and v["rate"] < 1 and v["nonverbal"] == ["sob"]
    assert {"rate", "pitch_st", "gain_db", "nonverbal", "scene", "level"} <= v.keys()


def test_choose_profile_and_settings() -> None:
    catalog = CATALOG.profiles()
    rng = random.Random(1)
    assert choose_profile(catalog, {"enabled": False}, 3, rng) is None
    picked = [choose_profile(catalog, {"enabled": True, "share": 1}, 5, random.Random(i)) for i in range(40)]
    ids = {p.id for p in picked if p}
    assert ids and not ids & {"suicidal", "child", "psychosis", "false_call"}  # кризисные — только явно
    assert choose_profile(catalog, {"enabled": True}, 3, rng, pinned="suicidal") is None
    assert choose_profile(catalog, {"enabled": True, "sensitive": ["suicidal"]}, 3, rng, pinned="suicidal")
    with pytest.raises(ValueError, match="Интенсивность"):
        check_settings({"intensity": 5})
    with pytest.raises(ValueError, match="Неизвестные профили"):
        check_settings({"profiles": ["ghost"]}, set(catalog))


# ------------------------------------------------------------------ реплики и валидатор


def test_remarks_and_validator() -> None:
    assert parse_remarks("[плачет] Он не дышит… [танцует]") == ("Он не дышит…", ["плачет"])
    assert validate("Я ИИ и не могу продолжать", legend=LEGEND, allowed={"what"}, intensity=2) == "выход из роли"
    assert validate("Я наглотаюсь таблеток", legend=LEGEND, allowed={"what"}, intensity=2) == "стоп-лист"
    blocked = validate("Тверская, дом семь!", legend=LEGEND, allowed={"what"}, intensity=2)
    assert blocked == "раскрыта закрытая тема"
    assert validate("Тверская, дом семь!", legend=LEGEND, allowed={"what", "address"}, intensity=2) is None


def router(llm: FakeLLM) -> ModelRouter:
    tasks = [AITask.APPLICANT_ACTOR, AITask.PSY_ACTS]
    return ModelRouter(
        profiles={t: TaskProfile(task=t, provider="demo") for t in tasks},
        clients={"demo": llm, "fake": FakeLLM()},
        default_provider="fake",
    )


def offline_director() -> PsyDirector:
    return PsyDirector(CATALOG, Actors(router(FakeLLM(name="fake"))))


# ------------------------------------------------------------------ полный разговор (офлайн) → оценка

T0 = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


def converse(profile_id: str, lines: list[str], *, ended_by: str = "operator", seed: int = 11) -> PsyAttempt:
    """Прогон реплик оператора через ведущего модификатора (офлайн) → попытка для блока оценки."""
    director = offline_director()
    p = CATALOG.get(profile_id)
    assert p is not None
    psy = start_psy(p, seed=seed, catalog_version=1, settings={"intensity": 2}, session_id=None)
    history: list[CallMessage] = []
    revealed = ["opening"]
    call_id = uuid4()
    turns: list[PsyTurn] = []
    last_topic: str | None = None
    for i, line in enumerate(lines):
        at = 8.0 * (i + 1)
        turn = asyncio.run(director.turn(psy, LEGEND, history, line, revealed, at, TurnSignals(), "scn"))
        assert turn is not None
        om, pm = turn.operator_meta, turn.party_meta
        last_topic = om["topic"]
        turns.append(
            PsyTurn(
                speaker="operator",
                text=line,
                at_s=at,
                acts=tuple(a["code"] for a in om["acts"]),
                quotes={a["code"]: a["quote"] for a in om["acts"]},
                level_before=om["level_before"],
                level_after=om["level_after"],
                topic=last_topic,
            )
        )
        turns.append(
            PsyTurn(
                speaker="party",
                text=turn.text,
                at_s=at + 1,
                level=pm["level"],
                emotional=pm["emotional"],
                remarks=tuple(pm["remarks"]),
                topic=last_topic,
                blocked=pm["blocked"],
            )
        )
        history += [
            CallMessage(call_id=call_id, speaker=Speaker.OPERATOR, text=line, at=T0 + timedelta(seconds=at)),
            CallMessage(call_id=call_id, speaker=Speaker.PARTY, text=turn.text, at=T0 + timedelta(seconds=at + 1)),
        ]
        revealed, psy = turn.revealed, turn.psy
        if turn.hung_up:
            ended_by = "party"
            break
    return PsyAttempt(profile=psy, turns=turns, ended_by=ended_by, services=["S101", "S103"])


GOOD = {
    "panic": [
        "Служба 112, я на линии, помощь уже направляю. Что случилось?",
        "Понимаю, вам страшно. Мне нужен адрес, чтобы направить помощь. Назовите адрес.",
        "Мне нужен адрес, чтобы направить помощь. Назовите адрес.",
        "Дышите со мной: медленный вдох и выдох. Назовите адрес.",
        "Тверская, дом 7, верно?",
        "Выйдите из квартиры и закройте за собой дверь. Бригада уже в пути.",
        "Вы всё делаете правильно. Есть пострадавшие?",
    ],
    "crying": [
        "Служба 112, я вас слушаю. Что случилось?",
        "Я здесь, я вас слушаю. Понимаю, как вам тяжело. Назовите адрес?",
        "Понял. Назовите адрес?",
        "Тверская, дом 7, верно?",
        "Я на линии, помощь уже направлена. Есть пострадавшие?",
    ],
    "aggression": [
        "Служба 112, я вас слушаю. Что случилось?",
        "Понимаю, вы ждёте, и это тяжело. Помощь уже направляю. Назовите адрес?",
        "Что сейчас важнее: назвать адрес или рассказать о пострадавших?",
        "Понимаю вас. Бригада уже в пути. Назовите адрес?",
        "Понимаю. Назовите адрес, чтобы бригада не потеряла время?",
        "Тверская, дом 7, верно?",
    ],
}
BAD_MUTATIONS = {
    "calm_down": ("Успокойтесь! Назовите адрес.", "CALM_DOWN"),
    "threat": ("Если будете кричать, я положу трубку.", "THREAT_HANGUP"),
    "rude": ("Вы что, глухой? Адрес назовите!", "RUDE"),
    "false_advice": ("Плесните на неё водой, чтобы пришла в себя.", "FALSE_ADVICE"),
}


@pytest.mark.parametrize("profile", sorted(GOOD))
def test_good_dialogue_passes_block(profile: str) -> None:
    r = assess_psy(converse(profile, GOOD[profile]))
    keys = {c.key: c for c in r.criteria}
    assert r.passed, (profile, r.score, r.errors)
    assert keys["psy_forbidden"].score == 1.0 and not r.critical
    assert keys["psy_outcome"].score is not None and keys["psy_outcome"].score > 0.5
    assert keys["psy_judge"].score is None  # офлайн: ИИ-судья «не проверено», в итог не входит


@pytest.mark.parametrize("profile", sorted(GOOD))
@pytest.mark.parametrize("mutation", sorted(BAD_MUTATIONS))
def test_mutations_are_detected(profile: str, mutation: str) -> None:
    """Бенчмарк мутаций (п. 3.5): вставка недопустимой реплики снижает балл и находится как ошибка."""
    line, code = BAD_MUTATIONS[mutation]
    good = assess_psy(converse(profile, GOOD[profile]))
    lines = [*GOOD[profile][:2], line, *GOOD[profile][2:]]
    bad = assess_psy(converse(profile, lines))
    forbidden = next(c for c in bad.criteria if c.key == "psy_forbidden")
    assert bad.score < good.score, (profile, mutation)
    assert forbidden.score is not None and forbidden.score < 1 and forbidden.errors
    p = CATALOG.get(profile)
    assert p is not None
    if code in p.critical:
        assert not bad.passed and forbidden.critical  # критическая ошибка — «не зачтено» блока


def test_stupor_requires_routing_and_suicidal_hangup_is_critical() -> None:
    r = assess_psy(converse("stupor", ["Служба 112, что случилось?", "Назовите адрес?"]))
    routing = next(c for c in r.criteria if c.key == "psy_routing")
    assert routing.score is not None and routing.score < 1 and any("психолог" in e for e in routing.errors)
    s = assess_psy(converse("suicidal", ["Служба 112, я вас слушаю.", "Понимаю. Где вы сейчас?"]))
    forbidden = next(c for c in s.criteria if c.key == "psy_forbidden")
    assert forbidden.critical and not s.passed  # положил трубку первым при кризисе — NENA-STA-001


def test_model_reply_is_used_only_if_it_passes_validation() -> None:
    llm = FakeLLM(name="demo", fixtures={AITask.APPLICANT_ACTOR: "[плачет] Тверская, дом семь, быстрее!"})
    director = PsyDirector(CATALOG, Actors(router(llm)))
    p = CATALOG.get("panic")
    assert p is not None
    psy = start_psy(p, seed=3, catalog_version=1, settings={}, session_id=None)
    turn = asyncio.run(director.turn(psy, LEGEND, [], "Успокойтесь!", ["opening"], 5, TurnSignals(), "s"))
    assert turn is not None
    assert "Тверская" not in turn.text  # уровень 5, адрес закрыт — модель раскрыла его, реплика заменена
    assert turn.party_meta["source"] == "offline"
    prompt = llm.calls[0][0][0].content
    assert "уровень 5 из 5" in prompt and "reference" not in prompt and "S101" not in prompt


def test_signals_from_voice_channel_become_events() -> None:
    director = offline_director()
    p = CATALOG.get("panic")
    assert p is not None
    psy = start_psy(p, seed=3, catalog_version=1, settings={}, session_id=None)
    turn = asyncio.run(
        director.turn(
            psy, LEGEND, [], "Назовите адрес", ["opening"], 5, TurnSignals(latency_ms=15_000, interrupted=True), "s"
        )
    )
    assert turn is not None
    assert {"DEAD_AIR", "INTERRUPT"} <= {a["code"] for a in turn.operator_meta["acts"]}


def test_offline_answer_matches_legend_when_topic_open() -> None:
    p = CATALOG.get("elderly")
    assert p is not None
    s = initial_state(p)
    assert "address" in gates(p, s)
    base = applicant_reply(LEGEND, "Назовите адрес", [])
    assert "Тверская" in base.text
