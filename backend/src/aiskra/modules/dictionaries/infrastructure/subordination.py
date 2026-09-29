"""Справочник подчинённости объектов из YAML (пп. 4.4, 8.4). Нет файла — нет правил."""

from __future__ import annotations

from functools import cache
from pathlib import Path

import yaml

from aiskra.modules.dictionaries.domain.subordination import SubordinationRule, parse_rules


@cache
def load_subordination(path: str) -> tuple[SubordinationRule, ...]:
    p = Path(path)
    if not p.exists():
        return ()
    return parse_rules(yaml.safe_load(p.read_text(encoding="utf-8")) or {})
