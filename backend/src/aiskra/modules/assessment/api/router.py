"""HTTP-адаптер автооценки (п. 3.4)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from aiskra.modules.assessment.api import deps
from aiskra.modules.assessment.application.commands.assess import AssessCard, AssessCardHandler, Settings
from aiskra.modules.assessment.application.commands.evaluate_session import (
    EvaluateSession,
    EvaluateSessionHandler,
    EvaluateSummary,
)
from aiskra.modules.assessment.application.commands.override import OverrideAssessment, OverrideAssessmentHandler
from aiskra.modules.assessment.application.ports.attempts import AssessmentRecord
from aiskra.modules.assessment.application.queries.assessments import (
    GetAssessment,
    GetAssessmentHandler,
    GroupInsights,
    GroupInsightsHandler,
    Insights,
)
from aiskra.modules.assessment.application.queries.reports import (
    GetSessionReport,
    GetSessionReportHandler,
    MyProgress,
    MyProgressHandler,
    ProgressView,
    SessionReport,
    report_csv,
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


Teacher = Annotated[Principal, Depends(require(Permission.RESULTS_READ_ALL))]
Checker = Annotated[Principal, Depends(require(Permission.CARDS_CHECK))]


class OverrideIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score: float = Field(ge=0, le=100)
    comment: str = Field(min_length=3, max_length=1000, description="Причина правки — видна обучающемуся")
    threshold: float = Field(default=PASS_THRESHOLD, ge=0, le=100)


@router.post(
    "/{assessment_id}/override", response_model=AssessmentRecord, summary="Экспертная оценка поверх автооценки"
)
async def override(
    assessment_id: UUID,
    body: OverrideIn,
    actor: Checker,
    meta: Meta,
    handler: Annotated[OverrideAssessmentHandler, Depends(deps.provide_override)],
) -> AssessmentRecord:
    return await handler(
        OverrideAssessment(
            actor=actor,
            assessment_id=assessment_id,
            score=body.score,
            comment=body.comment,
            threshold=body.threshold,
            meta=meta,
        )
    )


@router.post("/sessions/{session_id}/evaluate", response_model=EvaluateSummary, summary="Оценить все карточки занятия")
async def evaluate_session(
    session_id: UUID,
    actor: Checker,
    meta: Meta,
    handler: Annotated[EvaluateSessionHandler, Depends(deps.provide_evaluate_session)],
) -> EvaluateSummary:
    return await handler(EvaluateSession(actor=actor, session_id=session_id, meta=meta))


@router.get("/sessions/{session_id}/report", response_model=SessionReport, summary="Отчёт по занятию (п. 4.3)")
async def session_report(
    session_id: UUID, actor: Teacher, handler: Annotated[GetSessionReportHandler, Depends(deps.provide_report)]
) -> SessionReport:
    return await handler(GetSessionReport(actor=actor, session_id=session_id))


@router.get("/sessions/{session_id}/report.csv", summary="Отчёт по занятию в CSV (Excel)")
async def session_report_csv(
    session_id: UUID, actor: Teacher, handler: Annotated[GetSessionReportHandler, Depends(deps.provide_report)]
) -> Response:
    report = await handler(GetSessionReport(actor=actor, session_id=session_id))
    return Response(
        content=report_csv(report).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="session-{session_id}.csv"'},
    )


@router.get("/my/progress", response_model=ProgressView, summary="Мой прогресс: динамика баллов и слабые места")
async def my_progress(
    actor: CurrentPrincipal, handler: Annotated[MyProgressHandler, Depends(deps.provide_progress)]
) -> ProgressView:
    return await handler(MyProgress(actor=actor))
