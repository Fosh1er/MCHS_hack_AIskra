"""HTTP-адаптер автооценки (п. 3.4)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from aiskra.modules.assessment.api import deps
from aiskra.modules.assessment.application.commands.assess import AssessCard, AssessCardHandler, Settings
from aiskra.modules.assessment.application.commands.evaluate_session import (
    EvaluateSession,
    EvaluateSessionHandler,
    EvaluateSummary,
)
from aiskra.modules.assessment.application.commands.feedback import SaveFeedback, SaveFeedbackHandler
from aiskra.modules.assessment.application.commands.override import OverrideAssessment, OverrideAssessmentHandler
from aiskra.modules.assessment.application.ports.attempts import AssessmentRecord
from aiskra.modules.assessment.application.ports.feedback import FeedbackRecord
from aiskra.modules.assessment.application.queries.analytics import (
    AssignmentSuggestion,
    DebriefView,
    NormReport,
    NormReportHandler,
    NormReportView,
    ReadinessHandler,
    ReadinessQuery,
    ReadinessView,
    SessionDebrief,
    SessionDebriefHandler,
    StudentProfile,
    StudentProfileHandler,
    StudentProfileView,
    SuggestAssignment,
    SuggestAssignmentHandler,
)
from aiskra.modules.assessment.application.queries.assessments import (
    GetAssessment,
    GetAssessmentHandler,
    GroupInsights,
    GroupInsightsHandler,
    Insights,
)
from aiskra.modules.assessment.application.queries.feedback import (
    DraftFeedback,
    DraftFeedbackHandler,
    FeedbackDraft,
    FeedbackItem,
    MyFeedback,
    MyFeedbackHandler,
)
from aiskra.modules.assessment.application.queries.reports import (
    GetMySessionReport,
    GetMySessionReportHandler,
    GetSessionReport,
    GetSessionReportHandler,
    MyProgress,
    MyProgressHandler,
    MySessionReport,
    ProgressView,
    SessionReport,
    report_csv,
)
from aiskra.modules.assessment.application.queries.validation import ValidationHandler, ValidationQuery, ValidationView
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


@router.get(
    "/sessions/{session_id}/mine", response_model=MySessionReport, summary="Мои результаты по занятию и рекомендации"
)
async def my_session_report(
    session_id: UUID,
    actor: CurrentPrincipal,
    handler: Annotated[GetMySessionReportHandler, Depends(deps.provide_my_report)],
) -> MySessionReport:
    return await handler(GetMySessionReport(actor=actor, session_id=session_id))


# ------------------------------------------------------------------ отзыв преподавателя по занятию (specs/4.7)

Conductor = Annotated[Principal, Depends(require(Permission.LESSONS_CONDUCT))]


@router.post(
    "/sessions/{session_id}/students/{student_id}/feedback/draft",
    response_model=FeedbackDraft,
    summary="Черновик отзыва обучающемуся по занятию: ИИ, без модели — по правилам; ничего не публикует",
)
async def feedback_draft(
    session_id: UUID,
    student_id: UUID,
    actor: Conductor,
    handler: Annotated[DraftFeedbackHandler, Depends(deps.provide_feedback_draft)],
) -> FeedbackDraft:
    return await handler(DraftFeedback(actor=actor, session_id=session_id, student_id=student_id))


class FeedbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=10, max_length=3000, description="Текст отзыва — его увидит обучающийся")
    draft_text: str | None = Field(default=None, max_length=6000, description="С какого черновика начали")
    draft_source: Literal["ai", "rules"] | None = None
    draft_model: str | None = Field(default=None, max_length=200)


class FeedbackOut(BaseModel):
    session_id: UUID
    student_id: UUID
    text: str
    updated_at: datetime | None


def _out(r: FeedbackRecord) -> FeedbackOut:
    return FeedbackOut(session_id=r.session_id, student_id=r.student_id, text=r.text, updated_at=r.updated_at)


@router.put(
    "/sessions/{session_id}/students/{student_id}/feedback",
    response_model=FeedbackOut,
    summary="Сохранить отзыв обучающемуся по занятию (заменяет прежний; в аудит)",
)
async def feedback_save(
    session_id: UUID,
    student_id: UUID,
    body: FeedbackIn,
    actor: Conductor,
    meta: Meta,
    handler: Annotated[SaveFeedbackHandler, Depends(deps.provide_feedback_save)],
) -> FeedbackOut:
    saved = await handler(
        SaveFeedback(
            actor=actor,
            session_id=session_id,
            student_id=student_id,
            text=body.text,
            draft_text=body.draft_text,
            draft_source=body.draft_source,
            draft_model=body.draft_model,
            meta=meta,
        )
    )
    return _out(saved)


@router.get("/my/feedback", response_model=list[FeedbackItem], summary="Отзывы преподавателей по моим занятиям")
async def my_feedback(
    actor: Annotated[Principal, Depends(require(Permission.RESULTS_READ_OWN))],
    handler: Annotated[MyFeedbackHandler, Depends(deps.provide_my_feedback)],
) -> list[FeedbackItem]:
    return await handler(MyFeedback(actor=actor))


# ------------------------------------------------------------------ аналитика преподавателя (specs/4.5)


@router.get(
    "/analytics/norms", response_model=NormReportView, summary="Норматив / факт по времени (ПП РФ № 1931, форма 1/112)"
)
async def norm_report(
    actor: Teacher,
    handler: Annotated[NormReportHandler, Depends(deps.provide_norm_report)],
    days: Annotated[int, Query(ge=0, le=3650, description="Период, дней; 0 — все занятия")] = 30,
    session_id: UUID | None = None,
) -> NormReportView:
    return await handler(NormReport(actor=actor, days=days or None, session_id=session_id))


@router.get(
    "/analytics/students/{student_id}",
    response_model=StudentProfileView,
    summary="Профиль обучающегося по всем занятиям преподавателя",
)
async def student_profile(
    student_id: UUID, actor: Teacher, handler: Annotated[StudentProfileHandler, Depends(deps.provide_student_profile)]
) -> StudentProfileView:
    return await handler(StudentProfile(actor=actor, student_id=student_id))


@router.get(
    "/sessions/{session_id}/debrief", response_model=DebriefView, summary="Разбор занятия: характерные недостатки"
)
async def session_debrief(
    session_id: UUID, actor: Teacher, handler: Annotated[SessionDebriefHandler, Depends(deps.provide_debrief)]
) -> DebriefView:
    return await handler(SessionDebrief(actor=actor, session_id=session_id))


@router.get(
    "/analytics/suggest",
    response_model=AssignmentSuggestion,
    summary="Подбор задания по слабым местам: группы классификатора, сложность, фокус инструктажа",
)
async def suggest_assignment(
    actor: Teacher,
    handler: Annotated[SuggestAssignmentHandler, Depends(deps.provide_suggest)],
    student_id: Annotated[list[UUID], Query(min_length=1, max_length=100)],
) -> AssignmentSuggestion:
    return await handler(SuggestAssignment(actor=actor, student_ids=student_id))


@router.get(
    "/analytics/readiness",
    response_model=ReadinessView,
    summary="Готовность к допуску: оценка по шкале Программы подготовки ЕДДС и нормативам ПП № 1931",
)
async def readiness(
    actor: Teacher,
    handler: Annotated[ReadinessHandler, Depends(deps.provide_readiness)],
    student_id: Annotated[list[UUID] | None, Query(max_length=200, description="Нет — все обучающиеся")] = None,
    last: Annotated[int, Query(ge=3, le=100, description="Сколько последних оценённых карточек учитывать")] = 10,
    min_cards: Annotated[int, Query(ge=1, le=50, description="Меньше карточек — «недостаточно данных»")] = 5,
) -> ReadinessView:
    return await handler(ReadinessQuery(actor=actor, student_ids=student_id or [], last=last, min_cards=min_cards))


@router.get(
    "/analytics/validation",
    response_model=ValidationView,
    summary="Достоверность автооценки: бенчмарк ошибок, согласованность генератора, согласие с экспертом (п. 3.5)",
)
async def validation(
    _: Teacher,
    handler: Annotated[ValidationHandler, Depends(deps.provide_validation)],
    limit: Annotated[int, Query(ge=1, le=500, description="Сколько утверждённых сценариев взять")] = 50,
) -> ValidationView:
    return await handler(ValidationQuery(limit=limit))
