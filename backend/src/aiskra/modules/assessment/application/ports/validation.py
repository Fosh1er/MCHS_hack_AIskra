"""Порт валидации автооценки (п. 3.5): утверждённые сценарии с легендой, эталонами и пересчитанным автоподбором
служб — из training и dictionaries через адаптер composition root."""

from __future__ import annotations

from typing import Protocol

from aiskra.modules.assessment.domain.validation import ScenarioCase


class ValidationSource(Protocol):
    async def cases(self, limit: int) -> list[ScenarioCase]: ...
