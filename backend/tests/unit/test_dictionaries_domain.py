from pathlib import Path

import pytest
import yaml

from aiskra.modules.dictionaries.application.ports.reader import IncidentTypeRow
from aiskra.modules.dictionaries.application.queries.incident_types import build_tree
from aiskra.modules.dictionaries.domain.model import (
    DeliveryKind,
    IncidentCode,
    ServiceColumn,
    clean,
    parse_delivery,
    parse_main_services,
    search_form,
)
from aiskra.shared.errors import DomainError

DATA = Path(__file__).resolve().parents[3] / "data" / "dictionaries"


def test_incident_code_structure() -> None:
    c = IncidentCode("1010101")
    assert c.group == 1 and c.levels == (1, 1, 1)
    c2 = IncidentCode("14050300")
    assert c2.group == 14 and c2.levels == (5, 3, 0)
    with pytest.raises(DomainError):
        IncidentCode("12AB")


@pytest.mark.parametrize(
    "raw",
    [
        "карточка-112",
        "Карточка-112",
        "Карточки-112",
        "Картчока-112",
        "Картточка-112",
        "Карточка-122",
        "карточка -112",
        "карточка-113",
    ],
)
def test_card112_typos_are_normalized(raw: str) -> None:
    d = parse_delivery(raw)
    assert d is not None and d.kind is DeliveryKind.CARD_112 and d.service_type is None


def test_delivery_variants() -> None:
    assert parse_delivery(None) is None and parse_delivery("  ") is None
    assert parse_delivery("Нет реагирования").kind is DeliveryKind.NO_RESPONSE  # type: ignore[union-attr]
    d = parse_delivery(" пожар:  мусор\n")
    assert d is not None and d.kind is DeliveryKind.CLASSIFIED and d.service_type == "пожар: мусор"


def test_main_services_and_clean() -> None:
    assert parse_main_services("METRO, MZD") == ["METRO", "MZD"]
    assert parse_main_services(" ") == []
    assert clean("Дерево \n ") == "Дерево"
    assert search_form("Пожар-Квартира, ЁЛКА") == "пожар квартира елка"


def test_service_column_invariants() -> None:
    ServiceColumn(col=15, service="S101", header="МЧС", base="exclusive")
    ServiceColumn(col=16, service="S101", header="МЧС", flag="no_access")
    with pytest.raises(DomainError):
        ServiceColumn(col=15, service="S101", header="МЧС")  # базовой колонке нужен base
    with pytest.raises(DomainError):
        ServiceColumn(col=16, service="S101", header="МЧС", flag="no_access", base="always")


def row(code: str, s1: str | None, s2: str | None, s3: str | None) -> IncidentTypeRow:
    return IncidentTypeRow(
        code=code,
        group_id=1,
        group_title="Пожары",
        sign1=s1,
        sign2=s2,
        sign3=s3,
        final_type=None,
        ekp_type=None,
        response_scenario=None,
        main_services=[],
        visible_to_112=True,
        operator_hint=None,
    )


def test_questionnaire_tree() -> None:
    roots = build_tree(
        [
            row("1010101", "на улице", "мусор", "открытое пламя"),
            row("1010102", "на улице", "мусор", "дым"),
            row("1020100", "жилой дом", "квартира", None),
        ]
    )
    assert [r.label for r in roots] == ["на улице", "жилой дом"]
    trash = roots[0].children[0]
    assert trash.label == "мусор" and [c.codes for c in trash.children] == [["1010101"], ["1010102"]]
    assert roots[1].children[0].codes == ["1020100"]


def test_curated_yaml_is_consistent() -> None:
    enums = yaml.safe_load((DATA / "enums.yaml").read_text(encoding="utf-8"))["enums"]
    assert [v["code"] for v in enums["applicant_status"]] == [
        "witness",
        "victim",
        "relative",
        "acquaintance",
        "child",
        "participant",
    ]
    cols = yaml.safe_load((DATA / "classifier_columns.yaml").read_text(encoding="utf-8"))["columns"]
    flags = {f["code"] for f in enums["card_flag"]}
    assert all(c.get("flag") in flags for c in cols if c.get("flag"))
    card_types = yaml.safe_load((DATA / "card_types.yaml").read_text(encoding="utf-8"))["card_types"]
    assert len(card_types) == 51
