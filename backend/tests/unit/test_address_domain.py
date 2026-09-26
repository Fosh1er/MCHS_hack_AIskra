"""Адресный справочник (п. 1.2): разбор строки, номер дома, подпись, геометрия."""

from aiskra.modules.dictionaries.domain.address import (
    address_label,
    distance_m,
    geometry_bbox,
    house_key,
    parse_query,
    point_in_geometry,
    same_house_number,
)


def test_parse_street_house_building_structure() -> None:
    q = parse_query("ул. Новая Басманная, 6 к1 с2")
    assert q.street_terms == ["улица", "новая", "басманная"]
    assert (q.house, q.building, q.structure) == ("6", "1", "2")


def test_parse_compact_building_and_letter() -> None:
    q = parse_query("Щелковское ш 44а к2")
    assert q.street_terms == ["щелковское", "шоссе"]
    assert (q.house, q.building) == ("44А", "2")


def test_numbers_inside_street_name_are_not_house() -> None:
    q = parse_query("3-й Дорожный проезд, 1")
    assert q.street_terms[:2] == ["3", "й"] and q.house == "1"
    assert parse_query("улица 1905 года 10").house == "10"
    assert parse_query("Москва, Тверская").street_terms == ["тверская"]


def test_house_key_and_prefix() -> None:
    assert house_key("16А", "1", "2") == "16а к1 с2"
    assert same_house_number("13", "13") and same_house_number("13а", "13") and same_house_number("13/2 с1", "13")
    assert same_house_number("13 к1", "13") and not same_house_number("130", "13")


def test_label() -> None:
    assert address_label("Новая Басманная улица", "6", "1") == "Новая Басманная улица, 6 к1"
    assert address_label("Тверская улица", "") == "Тверская улица"


SQUARE = {
    "type": "Polygon",
    "coordinates": [
        [[37.0, 55.0], [38.0, 55.0], [38.0, 56.0], [37.0, 56.0], [37.0, 55.0]],
        [[37.4, 55.4], [37.6, 55.4], [37.6, 55.6], [37.4, 55.6], [37.4, 55.4]],
    ],
}


def test_point_in_polygon_with_hole() -> None:
    assert point_in_geometry(37.2, 55.2, SQUARE)
    assert not point_in_geometry(37.5, 55.5, SQUARE)  # «дырка»
    assert not point_in_geometry(38.5, 55.5, SQUARE)
    multi = {"type": "MultiPolygon", "coordinates": [SQUARE["coordinates"]]}
    assert point_in_geometry(37.2, 55.2, multi)
    assert geometry_bbox(SQUARE) == (37.0, 55.0, 38.0, 56.0)


def test_distance() -> None:
    assert 110_000 < distance_m(55.0, 37.0, 56.0, 37.0) < 112_000
