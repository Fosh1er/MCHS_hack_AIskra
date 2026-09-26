"""Запросы оценок (п. 3.4): последняя оценка карточки и инсайты по группе — частые ошибки и средние баллы
по критериям (для преподавателя, ТЗ: «инсайты ИИ по типичным ошибкам группы»)."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from uuid import UUID

from aiskra.modules.assessment.application.ports.attempts import AssessmentRecord, AssessmentRepository
from aiskra.shared.application import Query
from aiskra.shared.errors import NotFoundError
from aiskra.shared.security import Permission, Principal


@dataclass(frozen=True, kw_only=True)
class GetAssessment(Query):
    actor: Principal
    card_id: UUID
    role: str
    service_code: str | None = None


class GetAssessmentHandler:
    def __init__(self, repo: AssessmentRepository) -> None:
        self._repo = repo

    async def __call__(self, q: GetAssessment) -> AssessmentRecord:
        rec = await self._repo.latest(q.card_id, q.role, q.service_code)
        if rec is None or (rec.student_id != q.actor.user_id and not q.actor.can(Permission.RESULTS_READ_ALL)):
            raise NotFoundError("Оценки ещё нет", code="assessment_not_found")
        return rec


@dataclass(frozen=True, kw_only=True)
class GroupInsights(Query):
    limit: int = 500


@dataclass(frozen=True)
class CriterionStat:
    key: str
    title: str
    average: float  # 0…1
    checked: int


@dataclass(frozen=True)
class ErrorStat:
    text: str
    count: int


@dataclass(frozen=True)
class Insights:
    assessments: int
    average_score: float
    passed_share: float
    weakest: list[CriterionStat]
    frequent_errors: list[ErrorStat]


class GroupInsightsHandler:
    def __init__(self, repo: AssessmentRepository) -> None:
        self._repo = repo

    async def __call__(self, q: GroupInsights) -> Insights:
        records = await self._repo.recent(q.limit)
        if not records:
            return Insights(assessments=0, average_score=0, passed_share=0, weakest=[], frequent_errors=[])
        scores: dict[str, list[float]] = defaultdict(list)
        titles: dict[str, str] = {}
        errors: Counter[str] = Counter()
        for r in records:
            for c in r.details.get("criteria", []):
                if c.get("score") is not None:
                    scores[c["key"]].append(float(c["score"]))
                    titles[c["key"]] = c.get("title", c["key"])
                for e in c.get("errors", []):
                    errors[f"{c.get('title', c['key'])}: {e.split(';')[0].split(' — ')[0][:90]}"] += 1
        weakest = sorted(
            (
                CriterionStat(key=k, title=titles[k], average=round(sum(v) / len(v), 3), checked=len(v))
                for k, v in scores.items()
            ),
            key=lambda s: s.average,
        )[:5]
        return Insights(
            assessments=len(records),
            average_score=round(sum(r.score for r in records) / len(records), 1),
            passed_share=round(sum(r.passed for r in records) / len(records), 3),
            weakest=weakest,
            frequent_errors=[ErrorStat(text=t, count=n) for t, n in errors.most_common(8)],
        )
