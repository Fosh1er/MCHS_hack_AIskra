"""Достоверность автооценки (п. 3.5): бенчмарк мутаций на утверждённых сценариях, согласованность генератора и
согласие автооценки с экспертными правками преподавателей. Методика — `domain/validation.py`."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from aiskra.modules.assessment.application.ports.attempts import AssessmentRecord, AssessmentRepository
from aiskra.modules.assessment.application.ports.validation import ValidationSource
from aiskra.modules.assessment.domain.validation import (
    Benchmark,
    ExpertAgreement,
    expert_agreement,
    generator_summary,
    run_benchmark,
)
from aiskra.shared.application import Query


@dataclass(frozen=True, kw_only=True)
class ValidationQuery(Query):
    limit: int = 50  # сценариев банка в бенчмарке (план: тест-набор 30–50)


@dataclass(frozen=True)
class ValidationView:
    generated_at: datetime
    benchmark: Benchmark
    generator: list[dict[str, Any]]
    expert: ExpertAgreement
    notes: list[str]


def expert_pairs(records: list[AssessmentRecord]) -> list[tuple[float, float]]:
    """(автобалл до правки, балл эксперта) по последней версии оценки каждой карточки и роли."""
    latest: dict[tuple[UUID, str, str | None], AssessmentRecord] = {}
    for r in records:  # recent — от новых к старым
        latest.setdefault((r.card_id, r.role, r.service_code), r)
    out = []
    for r in latest.values():
        e = r.details.get("expert") or {}
        if "auto_score" in e and "score" in e:
            out.append((float(e["auto_score"]), float(e["score"])))
    return out


class ValidationHandler:
    def __init__(self, source: ValidationSource, repo: AssessmentRepository) -> None:
        self._source = source
        self._repo = repo

    async def __call__(self, q: ValidationQuery) -> ValidationView:
        cases = await self._source.cases(q.limit)
        expert = expert_agreement(expert_pairs(await self._repo.recent(10_000)))
        notes = [
            "Бенчмарк синтетический: ошибки вносятся по одной в карточку, заполненную точно по эталону; он проверяет,"
            " что правила оценки находят то, что должны, и не ругаются зря.",
            "Главная метрика на реальных данных — согласие с экспертом: растёт с каждой правкой преподавателя.",
            "ИИ-судья (смысл и грамотность описания) в бенчмарк не входит: без модели он не вызывается; проверка"
            " судьи на модели — `tools/validate_ai.py --judge`.",
        ]
        if expert.pairs < 30:
            notes.append(f"Экспертных правок пока {expert.pairs}; для устойчивой оценки нужно не меньше 30.")
        return ValidationView(
            generated_at=datetime.now(UTC),
            benchmark=run_benchmark(cases),
            generator=generator_summary(cases),
            expert=expert,
            notes=notes,
        )
