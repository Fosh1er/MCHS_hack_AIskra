from pathlib import Path

import pytest
import yaml

from aiskra.modules.incidents.domain.card import ApplicantStatus, IncidentCardData
from aiskra.shared.errors import DomainError

ENUMS = Path(__file__).resolve().parents[3] / "data" / "dictionaries" / "enums.yaml"


def sample() -> dict[str, object]:
    return {
        "phones": {"aon": "+79990001234"},
        "channel": "mts",
        "applicant": {"name": "Колесникова Зинаида", "status": "witness"},
        "victims": {"has": True, "count": 1},
        "card_types": ["101"],
        "incident_types": ["1020100"],
        "questionnaire": {"101": {"Где": "Дом"}},
        "card_flags": ["threat_to_people", "gasified"],
        "address": {"okrug": "TAO", "district": "vorono_vskoe", "house": "12", "flat": "34"},
        "description": "Дым из-под двери кв. 34, в квартире возможно пожилой мужчина, дом газифицирован. " * 2,
        "services": ["S101", "S104"],
    }


def test_roundtrip() -> None:
    card = IncidentCardData.from_dict(sample())
    assert card.applicant.status is ApplicantStatus.WITNESS
    again = IncidentCardData.from_dict(card.to_dict())
    assert again == card and card.to_dict()["applicant"]["status"] == "witness"


def test_ambulance_sees_only_first_100_chars() -> None:
    card = IncidentCardData.from_dict(sample())
    assert len(card.ambulance_excerpt) == 100 and card.description.startswith(card.ambulance_excerpt)


def test_invariants() -> None:
    with pytest.raises(DomainError):
        IncidentCardData.from_dict({**sample(), "victims": {"has": False, "count": 2}})
    with pytest.raises(DomainError):
        IncidentCardData.from_dict({**sample(), "applicant": {"status": "сосед"}})
    with pytest.raises(DomainError):
        IncidentCardData.from_dict({**sample(), "description": "x" * 2000})
    with pytest.raises(DomainError):
        IncidentCardData.from_dict({**sample(), "flags": {"refusal_103": True}})


def test_applicant_statuses_match_dictionary() -> None:
    codes = [v["code"] for v in yaml.safe_load(ENUMS.read_text(encoding="utf-8"))["enums"]["applicant_status"]]
    assert codes == [s.value for s in ApplicantStatus]
