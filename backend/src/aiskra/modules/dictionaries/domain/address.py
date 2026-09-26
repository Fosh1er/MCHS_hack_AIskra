"""Адресный справочник (п. 1.2): разбор строки «улица, дом», ключ дома, район по точке, расстояние.

Чистый Python: геометрия — лучевой алгоритм по упрощённым границам районов (GeoJSON Polygon / MultiPolygon),
точности 15–25 м достаточно для выбора района и территориальных служб."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

# Сокращения типов улиц, которые оператор набирает в единой строке (instr/image20): «ул.», «пр-т», «б-р» …
STREET_ABBR = {
    "ул": "улица",
    "пр": "проспект",
    "прт": "проспект",
    "просп": "проспект",
    "пер": "переулок",
    "бр": "бульвар",
    "бул": "бульвар",
    "ш": "шоссе",
    "пл": "площадь",
    "наб": "набережная",
    "прд": "проезд",
    "пр-д": "проезд",
    "туп": "тупик",
    "мкр": "микрорайон",
    "кв-л": "квартал",
    "аллея": "аллея",
}
STOP_WORDS = {"москва", "г", "город", "россия", "д", "дом", "вл", "владение"}

_TOKEN = re.compile(r"[0-9]+[а-яa-z]?(?:/[0-9]+[а-я]?)?|[а-яёa-z]+(?:-[а-яёa-z]+)*", re.IGNORECASE)
_HOUSE = re.compile(r"^[0-9]+[а-яa-z]?(?:/[0-9]+[а-я]?)?$", re.IGNORECASE)
_BUILDING_WORDS = {"к", "корп", "корпус"}
_STRUCTURE_WORDS = {"с", "стр", "строение", "соор"}


@dataclass(frozen=True)
class AddressQuery:
    """Разобранная строка поиска: слова улицы + номер дома (если набран)."""

    street_terms: list[str]
    house: str = ""
    building: str = ""
    structure: str = ""


def _norm(s: str) -> str:
    return s.lower().replace("ё", "е")


def parse_query(raw: str) -> AddressQuery:
    """«ул. Новая Басманная, 6 к1» → улица [«улица», «новая», «басманная»], дом «6», корпус «1».

    Номер дома — первое число после слов улицы; «к»/«корп» и «с»/«стр» за ним — корпус и строение.
    Числа в названии улицы («3-й Дорожный проезд», «1905 года») идут до слов и считаются частью улицы."""
    tokens = [_norm(t) for t in _TOKEN.findall(raw.replace(",", " "))]
    street: list[str] = []
    house = building = structure = ""
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        if not house and _HOUSE.match(tok) and street and not (nxt.endswith(("й", "я", "е", "го")) or nxt == "года"):
            house = tok.upper() if tok[-1].isalpha() else tok
        elif house and tok in _BUILDING_WORDS and nxt:
            building, i = nxt.upper(), i + 1
        elif house and tok in _STRUCTURE_WORDS and nxt:
            structure, i = nxt.upper(), i + 1
        elif house and re.fullmatch(r"к[0-9]+", tok):
            building = tok[1:]
        elif house and re.fullmatch(r"с[0-9]+", tok):
            structure = tok[1:]
        elif not house and tok not in STOP_WORDS:
            street.append(STREET_ABBR.get(tok.replace("-", ""), tok))
        i += 1
    return AddressQuery(street_terms=street, house=house, building=building, structure=structure)


def house_key(house: str, building: str = "", structure: str = "") -> str:
    """Ключ дома для поиска по префиксу: «16А», «1», «2» → «16а к1 с2»."""
    parts = [house.lower()]
    if building:
        parts.append(f"к{building.lower()}")
    if structure:
        parts.append(f"с{structure.lower()}")
    return " ".join(parts)


def same_house_number(key: str, prefix: str) -> bool:
    """Ключ дома продолжает набранный номер, не удлиняя число: «13» → «13», «13а», «13/2», «13 к1»; не «130»."""
    if not key.startswith(prefix):
        return False
    rest = key[len(prefix) :]
    return not rest or not (prefix[-1].isdigit() and rest[0].isdigit())


def address_label(street: str, house: str, building: str = "", structure: str = "") -> str:
    """Подпись как в подсказках АРМ: «Новая Басманная улица, 6 к1 с2»."""
    num = house + (f" к{building}" if building else "") + (f" с{structure}" if structure else "")
    return f"{street}, {num}" if num else street


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Расстояние по поверхности Земли (гаверсинус), метры."""
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def point_in_geometry(lon: float, lat: float, geometry: dict[str, Any]) -> bool:
    """Точка внутри GeoJSON Polygon / MultiPolygon (с учётом «дырок»)."""
    polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    for rings in polygons:
        if rings and _in_ring(lon, lat, rings[0]) and not any(_in_ring(lon, lat, hole) for hole in rings[1:]):
            return True
    return False


def geometry_bbox(geometry: dict[str, Any]) -> tuple[float, float, float, float]:
    """(min_lon, min_lat, max_lon, max_lat) внешних колец."""
    polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    xs = [p[0] for rings in polygons for p in rings[0]]
    ys = [p[1] for rings in polygons for p in rings[0]]
    return min(xs), min(ys), max(xs), max(ys)
