"""HTTP-адаптер автооценки (п. 3.4)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from aiskra.modules.assessment.api import deps
from aiskra.modules.assessment.application.commands.assess import AssessCard, AssessCardHandler, Settings
from aiskra.modules.assessment.application.ports.attempts import AssessmentRecord
from aiskra.modules.assessment.application.queries.assessments import (
    GetAssessment,
    GetAssessmentHandler,
    GroupInsights,
    GroupInsightsHandler,
    Insights,
)
from aiskra.modules.assessment.domain.scoring import PASS_THRESHOLD
from aiskra.shared.security import Permission, Principal
from aiskra.shared.web import CurrentPrincipal, Meta, require

router = APIRouter(prefix="/assessment", tags=["assessment"])


class EvaluateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str = Field(pattern="^(112|dds)$")
    service_code: str | None = Field(default=None, max_length=64)
    weights: dict[str, float] = Field(default_factory=dict, description="Веса критериев поверх значений по умолчанию")
    norm_seconds: float | None = Field(default=None, gt=0, le=3600)
    threshold: float = Field(default=PASS_THRESHOLD, ge=0, le=100)


@router.post(
    "/cards/{card_id}/evaluate", response_model=AssessmentRecord, summary="Автооценка карточки 112 или работы ДДС"
)
async def evaluate(
    card_id: UUID,
    body: EvaluateIn,
    actor: CurrentPrincipal,
    meta: Meta,
    handler: Annotated[AssessCardHandler, Depends(deps.provide_assess)],
) -> AssessmentRecord:
    settings = Settings(weights=body.weights, norm_seconds=body.norm_seconds, threshold=body.threshold)
    return await handler(
        AssessCard(
            actor=actor, card_id=card_id, role=body.role, service_code=body.service_code, settings=settings, meta=meta
        )
    )


@router.get("/cards/{card_id}", response_model=AssessmentRecord, summary="Последняя оценка")
async def get_assessment(
    card_id: UUID,
    actor: CurrentPrincipal,
    handler: Annotated[GetAssessmentHandler, Depends(deps.provide_get)],
    role: str = "112",
    service_code: str | None = None,
) -> AssessmentRecord:
    return await handler(GetAssessment(actor=actor, card_id=card_id, role=role, service_code=service_code))


@router.get("/insights", response_model=Insights, summary="Инсайты по группе: слабые критерии и частые ошибки")
async def insights(
    _: Annotated[Principal, Depends(require(Permission.RESULTS_READ_ALL))],
    handler: Annotated[GroupInsightsHandler, Depends(deps.provide_insights)],
) -> Insights:
    return await handler(GroupInsights())
