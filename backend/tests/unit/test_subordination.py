"""Подчинённость объектов (пп. 4.4, 8.4): правило из справочника → служба-«хозяин» объекта."""

from pathlib import Path

import pytest

from aiskra.modules.dictionaries.domain.subordination import SubordinationError, parse_rules, subordinate_services
from aiskra.modules.dictionaries.infrastructure.subordination import load_subordination

REPO = Path(__file__).resolve().parents[3]

RULES = parse_rules({"rules": [{"match": ["школ", "гимназ"], "service": "DEP_EDU", "note": "Департамент образования"}]})


def test_school_goes_to_education_department() -> None:
    hit = subordinate_services(RULES, "ГБОУ Школа № 1234")
    assert [r.service for r in hit] == ["DEP_EDU"]
    assert hit[0].note == "Департамент образования"


def test_no_object_or_no_match_adds_nothing() -> None:
    assert subordinate_services(RULES, None) == []
    assert subordinate_services(RULES, "  ") == []
    assert subordinate_services(RULES, "ТЦ «Европейский»") == []


def test_rule_without_service_is_rejected() -> None:
    with pytest.raises(SubordinationError):
        parse_rules({"rules": [{"match": ["школ"]}]})


def test_shipped_directory_is_empty_so_routing_is_unchanged() -> None:
    # справочника заказчика нет: автоподбор служб и эталоны сценариев не меняются
    assert load_subordination(str(REPO / "data/dictionaries/subordination.yaml")) == ()
    assert load_subordination(str(REPO / "data/dictionaries/no_such_file.yaml")) == ()
