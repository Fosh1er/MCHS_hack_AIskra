"""Доменная модель справочников: типы происшествий классификатора, матрица служб, территории.

Чистый Python. Правила разбора данных заказчика собраны здесь, чтобы их можно было тестировать без xlsx и БД.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from aiskra.shared.errors import DomainError

_WS = re.compile(r"\s+")
_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)
# «карточка-112» с опечатками заказчика:
# Карточки-112, Картчока-112, Картточка-112, Карточка-122, карточка -112, карточка-113
_CARD112 = re.compile(r"^к\w{4,9}\s*-\s*1\d\d$", re.IGNORECASE)
_SCENARIO = re.compile(r"^\d{1,2}_\d{1,3}$")
HIDDEN_FROM_112 = "не отображается оператору 112"


def clean(value: object) -> str | None:
    """Нормализация ячейки: пробелы, переводы строк, пустые строки → None."""
    if value is None:
        return None
    s = _WS.sub(" ", str(value)).strip()
    return s or None


def search_form(text: str) -> str:
    """Форма для поиска: регистр, ё→е, пунктуация → пробел. «Пожар-Квартира» ~ «пожар квартира»."""
    return _WS.sub(" ", _NON_WORD.sub(" ", text.lower().replace("ё", "е"))).strip()


@dataclass(frozen=True)
class IncidentCode:
    """Код типа происшествия: группа (1–2 цифры) + признак 1, 2, 3 (по 2 цифры). 1010101 → 1/01/01/01."""

    value: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"\d{7,8}", self.value):
            raise DomainError(f"Некорректный код типа происшествия: {self.value!r}", code="bad_incident_code")

    @property
    def group(self) -> int:
        return int(self.value[:-6])

    @property
    def levels(self) -> tuple[int, int, int]:
        v = self.value[-6:]
        return int(v[0:2]), int(v[2:4]), int(v[4:6])


class DeliveryKind(StrEnum):
    CARD_112 = "card112"  # служба получает карточку 112 без своего типа
    CLASSIFIED = "classified"  # служба получает карточку со своим типом (значение ячейки)
    NO_RESPONSE = "no_response"  # «нет реагирования»


@dataclass(frozen=True)
class Delivery:
    kind: DeliveryKind
    service_type: str | None = None


def parse_delivery(raw: object) -> Delivery | None:
    """Ячейка матрицы служб → вариант доставки. Пусто → служба не получает карточку (None)."""
    s = clean(raw)
    if s is None:
        return None
    if s.lower() == "нет реагирования":
        return Delivery(DeliveryKind.NO_RESPONSE)
    if _CARD112.match(s):
        return Delivery(DeliveryKind.CARD_112)
    return Delivery(DeliveryKind.CLASSIFIED, s)


def parse_main_services(raw: object) -> list[str]:
    """«METRO, MZD» → ["METRO", "MZD"]; пусто → []."""
    s = clean(raw)
    return [p.strip() for p in s.split(",") if p.strip()] if s else []


def is_valid_scenario_code(raw: str | None) -> bool:
    return bool(raw and _SCENARIO.fullmatch(raw))


@dataclass
class IncidentType:
    """Строка классификатора — конечный тип происшествия."""

    code: IncidentCode
    group_id: int
    sign1: str | None
    sign2: str | None
    sign3: str | None
    operator_hint: str | None
    final_type: str | None
    ekp_type: str | None
    response_scenario: str | None
    main_services: list[str]
    visible_to_112: bool
    routing: dict[int, Delivery] = field(default_factory=dict)  # Excel-колонка → доставка

    @property
    def title(self) -> str:
        return self.final_type or " · ".join(p for p in (self.sign1, self.sign2, self.sign3) if p) or self.code.value

    def search_text(self) -> str:
        parts = [self.code.value, self.sign1, self.sign2, self.sign3, self.final_type, self.ekp_type]
        return search_form(" ".join(p for p in parts if p))


@dataclass(frozen=True)
class ServiceColumn:
    """Колонка матрицы: чья она, при каком признаке применяется и как ведёт себя базовая колонка."""

    col: int
    service: str
    header: str
    recipient: str | None = None
    flag: str | None = None
    base: str | None = None  # exclusive | always (только для flag is None)
    audience: str = "card"

    def __post_init__(self) -> None:
        if self.flag is None and self.base not in {"exclusive", "always"}:
            raise DomainError(f"Колонка {self.col}: базовой колонке нужен base exclusive|always", code="bad_column")
        if self.flag is not None and self.base is not None:
            raise DomainError(f"Колонка {self.col}: base задаётся только для базовой колонки", code="bad_column")


TERRITORIAL_SERVICES = frozenset({"territorial", "territorial_tinao", "territorial_roads"})
