"""Достоверность автооценки (п. 3.5): бенчмарк мутаций, κ Коэна, согласие с экспертом, критические ошибки,
согласованность генератора — на эталоне, собранном вручную."""

from aiskra.modules.assessment.domain.scoring import PASS_THRESHOLD, WEIGHTS_112, assess_card_112, finish
from aiskra.modules.assessment.domain.validation import (
    ScenarioCase,
    cohen_kappa,
    expert_agreement,
    generator_checks,
    perfect_card,
    run_benchmark,
)

REF = {
    "card_types": ["101"],
    "incident_types": ["10050001"],
    "questionnaire": {},
    "card_flags": ["victims", "threat"],
    "applicant": {"name": "Морозов Андрей", "status": "victim"},
    "victims": {"has": True, "count": 2},
    "address": {"street": "Бережковская набережная", "house": "12", "okrug": "ZAO", "district": "dorogomilovo"},
    "description_keywords": ["квартира", "дым", "набережная"],
    "services": [
        {"code": "S101", "short": "Служба 101", "main": True},
        {"code": "S103", "short": "Служба 103", "main": False},
    ],
    "final_type": "Пожар в квартире",
}
DDS = {"main_service": "S101", "first_status": "accepted", "expected_calls": ["brigade"]}
LEGEND = {
    "applicant": {"name": "Морозов Андрей", "status": "victim"},
    "address": {"street": "Бережковская набережная", "house": "12", "district": "dorogomilovo"},
    "victims": {"has": True, "count": 2},
    "opening": "Алло! Горит квартира, дым на всю набережную!",
    "what": "Пожар в квартире, сильный дым",
}


def test_benchmark_on_handmade_reference() -> None:
    b = run_benchmark([ScenarioCase(LEGEND, REF, DDS, {"S101", "S103"})])
    assert b.specificity_112 == 1 and b.specificity_dds == 1  # верная работа — без замечаний, 100 баллов
    assert b.detection == 1 and b.localization == 1
    assert b.verdict_accuracy == 1 and b.verdict_kappa == 1 and b.critical_caught == 1
    keys = {m["key"] for m in b.mutations}
    assert {"no_main_service", "missed_victims", "rejected", "very_slow"} <= keys
    assert b.cases == len(b.mutations)  # по одной мутации каждого вида на сценарий


def test_critical_error_fails_regardless_of_score() -> None:
    data, _ = perfect_card(REF)
    criteria = assess_card_112(data, ["S103"], 40, REF, {"address", "what", "victims"})
    r = finish("112", criteria, WEIGHTS_112, True)
    assert "services" in r.critical and not r.passed and r.score <= PASS_THRESHOLD - 1


def test_description_counts_only_spoken_facts_and_keeps_street_words() -> None:
    data, services = perfect_card(REF)
    data["description"] = "Горит квартира, дым на набережной"
    full = {c.key: c for c in assess_card_112(data, services, 40, REF, None)}
    assert full["description"].score == 1  # «набережная» не вырезается нормализацией адреса
    data["description"] = "Горит квартира, дым"
    heard = {c.key: c for c in assess_card_112(data, services, 40, REF, None, spoken="Горит квартира, дым")}
    assert heard["description"].score == 1  # «набережная» заявитель не говорил — не требуется


def test_kappa_and_expert_agreement() -> None:
    assert cohen_kappa([(True, True), (False, False)]) == 1
    assert cohen_kappa([(True, False), (False, True)]) == -1
    assert cohen_kappa([(True, True), (True, True)]) is None  # вырожденная разметка
    e = expert_agreement([(90, 80), (60, 75), (40, 30)])
    assert e.pairs == 3 and e.mae == 11.7 and e.verdict_agreement == round(2 / 3, 3)
    assert expert_agreement([]).mae is None


def test_generator_checks_catch_inconsistent_legend() -> None:
    ok = generator_checks(ScenarioCase(LEGEND, REF, DDS, {"S101", "S103"}))
    assert all(v for v in ok.values())
    bad_legend = {**LEGEND, "victims": {"has": False, "count": 0}, "address": {**LEGEND["address"], "house": "7"}}
    bad = generator_checks(ScenarioCase(bad_legend, REF, DDS, {"S101"}))
    assert bad["victims"] is False and bad["address"] is False and bad["routing"] is False
