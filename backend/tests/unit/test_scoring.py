"""Автооценка по эталону (п. 3.4): формулы критериев карточки 112 и работы ДДС."""

from datetime import UTC, datetime, timedelta

from aiskra.modules.assessment.domain.scoring import (
    WEIGHTS_112,
    WEIGHTS_DDS,
    Criterion,
    StatusStep,
    assess_card_112,
    assess_dds,
    f1,
    finish,
    norm_text,
    timing_score,
    total,
)

REF = {
    "card_types": ["101"],
    "incident_types": ["1010101"],
    "final_type": "пожар: мусор",
    "card_flags": ["victims"],
    "applicant": {"name": "Козлов Игорь", "status": "witness"},
    "victims": {"has": True, "count": 2},
    "address": {"street": "Новая Басманная улица", "house": "13", "district": "basmannyy"},
    "services": [{"code": "S101", "main": True}, {"code": "S103", "main": False}],
    "description_keywords": ["мусор", "открытое", "пламя"],
}
CARD = {
    "card_types": ["101"],
    "incident_types": ["1010101"],
    "card_flags": ["victims"],
    "applicant": {"name": "Козлов Игорь", "status": "witness"},
    "victims": {"has": True, "count": 2},
    "address": {"street": "ул. Новая Басманная", "house": "13", "district": "basmannyy"},
    "description": "Во дворе горит мусор, открытое пламя, двое пострадавших",
}


def by_key(criteria: list[Criterion]) -> dict[str, Criterion]:
    return {c.key: c for c in criteria}


def test_helpers() -> None:
    assert norm_text("ул. Новая Басманная") == norm_text("Новая Басманная улица") == "новая басманная"
    assert f1({"a", "b"}, {"a", "c"})[0] == 0.5
    assert timing_score(60, 80) == 1 and timing_score(160, 80) == 0.5 and timing_score(400, 80) == 0
    assert total([Criterion("type", 1), Criterion("grammar", None)], WEIGHTS_112) == 100


def test_perfect_card_scores_100() -> None:
    crit = assess_card_112(CARD, ["S101", "S103"], 60, REF, {"address", "what", "victims"})
    r = finish("112", crit, WEIGHTS_112, True)
    assert r.score == 100 and r.passed and r.errors == []


def test_errors_are_explained() -> None:
    card = {
        **CARD,
        "incident_types": ["1010102"],
        "card_flags": [],
        "victims": {"has": False, "count": 0},
        "address": {"street": "Тверская улица", "house": "1"},
        "description": "",
    }
    crit = by_key(
        assess_card_112(
            card, ["S101", "S104"], 200, REF, {"address"}, names={"S103": "Служба 103", "S104": "Служба 104"}
        )
    )
    assert crit["type"].score == 0.5 and "эталон" in crit["type"].errors[0]
    assert "Служба 103" in crit["services"].errors[0] and "Служба 104" in crit["services"].errors[1]
    assert crit["address"].score == 0 and crit["victims"].score == 0
    assert "что случилось" in crit["interview"].errors[0] and crit["timing"].score < 1
    assert finish("112", list(crit.values()), WEIGHTS_112, True).passed is False


def test_card_without_reference_checks_only_timing() -> None:
    crit = assess_card_112(CARD, [], 40, None, None)
    assert [c.key for c in crit] == ["timing"]


T0 = datetime(2026, 9, 27, 10, 0, tzinfo=UTC)


def step(status: str, sec: int, order: str | None = None, comment: str | None = "ок") -> StatusStep:
    return StatusStep(status, T0 + timedelta(seconds=sec), order, comment)


def test_dds_full_chain_in_time() -> None:
    hist = [
        step("added", 0, comment=None),
        step("received", 5, comment=None),
        step("accepted", 20, "7"),
        step("response_started", 60),
        step("arrived", 120),
        step("works_in_progress", 180),
        step("works_completed", 240),
    ]
    crit = assess_dds(hist, T0, {"first_status": "accepted", "expected_calls": ["brigade"]}, ["brigade"])
    r = finish("dds", crit, WEIGHTS_DDS, True)
    assert r.score == 100 and r.errors == []


def test_dds_mistakes() -> None:
    hist = [step("added", 0, comment=None), step("accepted", 95, None, None), step("arrived", 100)]
    crit = by_key(assess_dds(hist, T0, {"first_status": "accepted", "expected_calls": ["brigade"]}, []))
    assert crit["reaction"].score < 1 and "95 с" in crit["reaction"].errors[0]
    assert crit["order_no"].score == 0 and crit["calls"].score == 0
    assert "Работы завершены" in crit["chain"].errors[0]
    assert crit["comments"].score == 0.5


def test_dds_rejection_when_should_react() -> None:
    crit = by_key(assess_dds([step("rejected", 10)], T0, {"first_status": "accepted"}, []))
    assert crit["decision"].score == 0 and "calls" not in crit
