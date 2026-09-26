"""Правило применения матрицы служб классификатора (п. 1.5, используется карточкой 112 в п. 1.1).

Строка классификатора (конечный тип) содержит непустые ячейки в колонках служб. Колонка применяется:
- `base: always` — всегда;
- колонка признака (`flag`) — если признак выбран в карточке;
- `base: exclusive` — если не выбран ни один признак этой службы, у которого в этой строке есть ячейка.
  Признак с пустой ячейкой на доставку не влияет, поэтому базовую колонку не отключает.

Служба попадает в карточку, если хотя бы одна применённая колонка содержит доставку, отличную
от «нет реагирования». Колонки `audience: monitoring` (информационные подписчики) не показываются
на панели служб — это гипотеза из specs/0.2 §8, её подтверждает заказчик.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection, Iterable
from dataclasses import dataclass

from aiskra.modules.dictionaries.domain.model import DeliveryKind

AUDIENCE_MONITORING = "monitoring"
TINAO_OKRUGS = frozenset({"NAO", "TAO"})


@dataclass(frozen=True, kw_only=True)
class Cell:
    """Непустая ячейка строки классификатора вместе с разметкой её колонки."""

    col: int
    service: str
    flag: str | None
    base: str | None
    audience: str
    delivery: DeliveryKind
    service_type: str | None = None


@dataclass(frozen=True, kw_only=True)
class Hit:
    """Применённая колонка: служба получает карточку."""

    service: str
    col: int
    flag: str | None
    service_type: str | None
    monitoring: bool


def applicable(cells: Iterable[Cell], flags: Collection[str]) -> list[Hit]:
    by_service: dict[str, list[Cell]] = defaultdict(list)
    for c in cells:
        by_service[c.service].append(c)
    hits: list[Hit] = []
    for service, service_cells in by_service.items():
        chosen_flags = {c.flag for c in service_cells if c.flag is not None and c.flag in flags}
        for c in sorted(service_cells, key=lambda x: x.col):
            if c.flag is not None:
                applies = c.flag in chosen_flags
            elif c.base == "always":
                applies = True
            else:
                applies = not chosen_flags
            if applies and c.delivery is not DeliveryKind.NO_RESPONSE:
                hits.append(
                    Hit(
                        service=service,
                        col=c.col,
                        flag=c.flag,
                        service_type=c.service_type,
                        monitoring=c.audience == AUDIENCE_MONITORING,
                    )
                )
    return hits


def territorial_applies(service: str, okrug: str | None) -> bool:
    """«Территориальные ОИВ» — для Москвы без ТиНАО, «… ТиНАО» — только для ТиНАО; дороги — для всех округов."""
    if service == "territorial":
        return okrug not in TINAO_OKRUGS
    if service == "territorial_tinao":
        return okrug in TINAO_OKRUGS
    return True
