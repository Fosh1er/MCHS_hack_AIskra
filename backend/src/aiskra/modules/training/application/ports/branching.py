"""Порт каталога шаблонов ветвления (F5): источник — data/dictionaries/branch_templates.yaml."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from aiskra.modules.training.domain.branching import Template


class BranchCatalog(Protocol):
    @property
    def version(self) -> int: ...

    def templates(self) -> dict[str, Template]: ...

    def get(self, template_id: str) -> Template | None: ...

    def snapshot(self, template_id: str, legend: Mapping[str, Any]) -> dict[str, Any]:
        """Копия шаблона для сценария: плейсхолдеры заполнены по легенде, источники вложены."""
        ...
