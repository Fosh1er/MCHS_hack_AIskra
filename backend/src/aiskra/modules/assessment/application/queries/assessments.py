"""Запросы оценок (п. 3.4): последняя оценка карточки и инсайты по группе — частые ошибки и средние баллы
по критериям (для преподавателя, ТЗ: «инсайты ИИ по типичным ошибкам группы»)."""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from uuid import UUID

from pydantic import BaseModel, Field

from aiskra.ai.ports import ChatMessage
from aiskra.ai.prompts import load_prompt
from aiskra.ai.router import ModelRouter
from aiskra.ai.tasks import AITask
from aiskra.modules.assessment.application.ports.attempts import AssessmentRecord, AssessmentRepository
from aiskra.modules.assessment.domain.insights import rules_insights
from aiskra.shared.application import Query
from aiskra.shared.errors import ExternalServiceError, NotFoundError
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
    # ТЗ 3.13, 7.3: выводы по типичным ошибкам группы — моделью (задача insights) или правилами без неё
    summary: str = ""
    insights: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    source: str = "rules"  # ai | rules
    model: str | None = None


class InsightsOut(BaseModel):
    summary: str = Field(max_length=600)
    insights: list[str] = Field(default_factory=list, max_length=5)
    actions: list[str] = Field(default_factory=list, max_length=5)


log = logging.getLogger(__name__)


class GroupInsightsHandler:
    def __init__(self, repo: AssessmentRepository, router: ModelRouter | None = None) -> None:
        self._repo = repo
        self._router = router

    async def _explain(self, base: Insights) -> Insights:
        """Сводка → выводы. В модель уходят только цифры и тексты ошибок, без ФИО; при сбое — правила."""
        r = rules_insights(
            [(w.key, w.title, w.average) for w in base.weakest],
            [(e.text, e.count) for e in base.frequent_errors],
            base.average_score,
            base.passed_share,
        )
        out = Insights(**{**base.__dict__, "summary": r.summary, "insights": r.insights, "actions": r.actions})
        model = self._router.for_task(AITask.INSIGHTS) if self._router else None
        if model is None or model.provider_name == "fake":
            return out
        facts = {
            "попыток": base.assessments,
            "средний_балл": base.average_score,
            "доля_зачтённых": base.passed_share,
            "слабые_критерии": [
                {"критерий": w.title, "средний_балл": w.average, "проверок": w.checked} for w in base.weakest
            ],
            "частые_ошибки": [{"ошибка": e.text, "раз": e.count} for e in base.frequent_errors],
        }
        try:
            result = await model.complete(
                [
                    ChatMessage(role="system", content=load_prompt(AITask.INSIGHTS, model.profile.prompt_version)),
                    ChatMessage(role="user", content=json.dumps(facts, ensure_ascii=False)),
                ],
                schema=InsightsOut,
            )
            ai = (
                result.parsed
                if isinstance(result.parsed, InsightsOut)
                else InsightsOut.model_validate_json(result.text)
            )
        except (ExternalServiceError, ValueError) as e:
            log.warning("инсайты моделью не получены, выводы — правилами: %s", e)
            return out
        if not ai.summary.strip():
            return out
        return Insights(
            **{
                **base.__dict__,
                "summary": ai.summary.strip(),
                "insights": [x.strip() for x in ai.insights if x.strip()],
                "actions": [x.strip() for x in ai.actions if x.strip()],
                "source": "ai",
                "model": model.model_id,
            }
        )

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
        base = Insights(
            assessments=len(records),
            average_score=round(sum(r.score for r in records) / len(records), 1),
            passed_share=round(sum(r.passed for r in records) / len(records), 3),
            weakest=weakest,
            frequent_errors=[ErrorStat(text=t, count=n) for t, n in errors.most_common(8)],
        )
        return await self._explain(base)
