"""Каталог шаблонов ветвления из YAML (F5, ADR-0014). Граф каждого шаблона проверяется при первом чтении: шаблон
с тупиком или недостижимым итогом — отказ запуска с понятным сообщением, а не ситуация без исхода на занятии."""

from __future__ import annotations

from collections.abc import Mapping
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from aiskra.modules.training.domain.branching import BranchTemplateError, Template, instantiate, parse_catalog


@cache
def _load(path: str) -> tuple[int, dict[str, Template], dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        raise BranchTemplateError(f"Нет каталога шаблонов ветвления: {p}")
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    version, templates = parse_catalog(raw)
    return version, templates, raw


class YamlBranchCatalog:
    def __init__(self, path: Path) -> None:
        self._version, self._templates, self._raw = _load(str(path))

    @property
    def version(self) -> int:
        return self._version

    def templates(self) -> dict[str, Template]:
        return dict(self._templates)

    def get(self, template_id: str) -> Template | None:
        return self._templates.get(template_id)

    def snapshot(self, template_id: str, legend: Mapping[str, Any]) -> dict[str, Any]:
        raw = (self._raw.get("templates") or {})[template_id]
        return instantiate(template_id, raw, self._raw.get("sources") or {}, legend)
