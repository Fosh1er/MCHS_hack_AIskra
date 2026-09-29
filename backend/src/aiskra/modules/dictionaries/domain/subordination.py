"""Подчинённость объектов (пп. 4.4, 8.4 ТЗ): объект по адресу карточки → служба-«хозяин» объекта.

Пример ТЗ: школа → Департамент образования. Справочника подчинённости заказчик не передал, поэтому
файл `data/dictionaries/subordination.yaml` поставляется пустым и автоподбор служб работает как раньше.
Когда справочник появится, его строки переносятся в файл — код менять не нужно.

Правило срабатывает, если в поле «Объект» карточки есть одно из слов `match` (без учёта регистра,
по началу слова: «школ» находит «школа», «школе», «школьный»).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


class SubordinationError(ValueError):
    pass


@dataclass(frozen=True, kw_only=True)
class SubordinationRule:
    match: tuple[str, ...]
    service: str  # код службы из services_*.yaml
    note: str  # кому подчинён объект — пишется в причину подбора службы


def parse_rules(raw: Mapping[str, Any]) -> tuple[SubordinationRule, ...]:
    rules = []
    for i, r in enumerate(raw.get("rules") or [], 1):
        words = tuple(str(w).strip().lower() for w in (r.get("match") or []) if str(w).strip())
        service = str(r.get("service") or "").strip()
        if not words or not service:
            raise SubordinationError(f"subordination.yaml, правило {i}: нужны match и service")
        rules.append(SubordinationRule(match=words, service=service, note=str(r.get("note") or service)))
    return tuple(rules)


def subordinate_services(rules: Iterable[SubordinationRule], object_name: str | None) -> list[SubordinationRule]:
    """Правила, которые подходят объекту карточки; пустой объект — ни одного."""
    if not object_name or not object_name.strip():
        return []
    words = re.findall(r"\w+", object_name.lower())
    return [r for r in rules if any(w.startswith(m) for m in r.match for w in words)]
