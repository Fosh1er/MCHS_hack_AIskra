"""Правило матрицы служб (domain/routing.py) на синтетических ячейках."""

from aiskra.modules.dictionaries.domain.model import DeliveryKind
from aiskra.modules.dictionaries.domain.routing import Cell, applicable, territorial_applies

C112 = DeliveryKind.CARD_112


def cell(col: int, service: str, *, flag: str | None = None, base: str | None = "exclusive", **kw: object) -> Cell:
    return Cell(
        col=col,
        service=service,
        flag=flag,
        base=None if flag else base,
        audience=str(kw.get("audience", "card")),
        delivery=kw.get("delivery", C112),  # type: ignore[arg-type]
    )


ROW = [
    cell(15, "S101"),  # базовая «признак не выбран»
    cell(16, "S101", flag="no_access"),
    cell(22, "S102"),
    cell(26, "S103", flag="victims"),
    cell(48, "MGTS", base="always"),
    cell(60, "MAYOR_OFFICE", base="always", audience="monitoring"),
    cell(56, "CODD", base="always", delivery=DeliveryKind.NO_RESPONSE),
]


def services(flags: set[str]) -> list[tuple[str, int]]:
    return [(h.service, h.col) for h in applicable(ROW, flags) if not h.monitoring]


def test_without_flags_base_columns_apply() -> None:
    assert services(set()) == [("S101", 15), ("S102", 22), ("MGTS", 48)]


def test_flag_replaces_exclusive_base_and_adds_flag_services() -> None:
    assert services({"no_access", "victims"}) == [("S101", 16), ("S102", 22), ("S103", 26), ("MGTS", 48)]


def test_flag_without_cell_in_row_does_not_disable_base() -> None:
    """У S102 в строке нет колонки «правонарушение» — признак не влияет, базовая колонка остаётся."""
    assert ("S102", 22) in services({"offense"})


def test_no_response_and_monitoring() -> None:
    hits = applicable(ROW, set())
    assert "CODD" not in {h.service for h in hits}
    assert [h.service for h in hits if h.monitoring] == ["MAYOR_OFFICE"]


def test_territorial_columns_split_by_tinao() -> None:
    assert territorial_applies("territorial", "CAO") and not territorial_applies("territorial", "NAO")
    assert territorial_applies("territorial_tinao", "TAO") and not territorial_applies("territorial_tinao", "CAO")
    assert territorial_applies("territorial_roads", None)
