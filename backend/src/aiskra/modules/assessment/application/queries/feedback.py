"""Отзыв преподавателя по занятию (п. 4.7): черновик от ИИ и отзывы в истории обучающегося.

Черновик ничего не меняет и не публикует: обучающийся видит отзыв только после «сохранить» (`SaveFeedback`).
Модель получает факты без ФИО. Без модели (изолированный контур) или при её ошибке черновик строится
по правилам из тех же фактов — `domain/feedback.py`.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from aiskra.ai.ports import ChatMessage
from aiskra.ai.prompts import load_prompt
from aiskra.ai.router import ModelRouter
from aiskra.ai.tasks import AITask
from aiskra.modules.assessment.application.ports.attempts import AssessmentRepository
from aiskra.modules.assessment.application.ports.feedback import FeedbackRecord, FeedbackStore
from aiskra.modules.assessment.application.ports.reports import ReportParticipant, SessionFacts, SessionFactsSource
from aiskra.modules.assessment.application.queries.reports import build_report
from aiskra.modules.assessment.domain.feedback import (
    CardFacts,
    DraftParts,
    FeedbackFacts,
    PreviousFeedback,
    compose,
    rules_draft,
    summarize,
)
from aiskra.modules.assessment.domain.scoring import PASS_THRESHOLD, TITLES
from aiskra.shared.application import Query
from aiskra.shared.errors import ExternalServiceError, NotFoundError
from aiskra.shared.security import Principal

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeedbackContext:
    facts: SessionFacts
    person: ReportParticipant
    summary: FeedbackFacts
    previous: FeedbackRecord | None
    not_assessed: int


async def feedback_context(
    source: SessionFactsSource,
    repo: AssessmentRepository,
    store: FeedbackStore,
    *,
    actor: Principal,
    session_id: UUID,
    student_id: UUID,
) -> FeedbackContext:
    """Факты для отзыва. Только преподаватель, который вёл занятие, и только для участника занятия."""
    facts = await source.session(session_id)
    if facts is None or facts.teacher_id != actor.user_id:
        raise NotFoundError("Занятие не найдено", code="session_not_found")
    person = next((p for p in facts.participants if p.student_id == student_id), None)
    if person is None:
        raise NotFoundError("Обучающийся не участвовал в занятии", code="participant_not_found")
    report = await build_report(facts, repo, only=student_id)
    cards = [
        CardFacts(
            number=c.card_number,
            score=c.score,
            passed=c.passed,
            processing_s=c.processing_s,
            norm_s=c.norm_s,
            errors=c.errors,
            criteria=c.criteria,
            critical=c.critical,
            expert_comment=c.expert_comment,
        )
        for s in report.students
        for c in s.cards
    ]
    previous = next(
        (
            r
            for r in await store.for_student(student_id)
            if r.teacher_id == actor.user_id and r.session_id != session_id and _earlier(r.session_started_at, facts)
        ),
        None,
    )
    prev = (
        PreviousFeedback(
            session_title=previous.session_title,
            focus=[str(k) for k in previous.details.get("focus", [])],
            criteria={str(k): float(v) for k, v in (previous.details.get("criteria") or {}).items()},
        )
        if previous
        else None
    )
    threshold = float(facts.settings.get("threshold", PASS_THRESHOLD))
    return FeedbackContext(
        facts=facts,
        person=person,
        summary=summarize(facts.title, threshold, cards, prev),
        previous=previous,
        not_assessed=sum(s.not_assessed for s in report.students),
    )


def _earlier(started: datetime | None, facts: SessionFacts) -> bool:
    return started is None or facts.started_at is None or started < facts.started_at


def redact(text: str, full_name: str) -> str:
    """ФИО обучающегося — вне модели (docs/rules/ai.md): имя может оказаться в замечании или комментарии."""
    for part in (p for p in re.split(r"\s+", full_name) if len(p) >= 3):
        text = re.sub(rf"\b{re.escape(part)}\b", "[ФИО]", text, flags=re.IGNORECASE)
    return text


def model_facts(f: FeedbackFacts, full_name: str) -> dict[str, Any]:
    """Что уходит в модель: числа, критерии, замечания и советы. Без ФИО и без названия занятия — в нём бывает ФИО
    («Работа над ошибками: …»)."""
    return {
        "карточек": f.cards,
        "оценено": f.assessed,
        "средний_балл": f.avg_score,
        "порог": f.threshold,
        "зачтено": f.passed,
        "время": {"норматив_с": f.norm_s, "в_нормативе": f.in_norm, "карточек_со_временем": f.timed}
        if f.timed
        else None,
        "получилось": [{"критерий": TITLES.get(k, k), "процентов": round(v * 100)} for k, v in f.strengths],
        "подтянуть": [
            {
                "критерий": x.title,
                "процентов": round(x.average * 100),
                "замечание": redact(x.example, full_name),
                "карточки": x.cards,
                "критическая": x.critical,
                "совет": x.advice,
            }
            for x in f.focus
        ],
        "прошлый_отзыв": [
            {"критерий": p.title, "было_процентов": round(p.before * 100), "стало_процентов": round(p.now * 100)}
            for p in f.progress
        ]
        or None,
        "комментарии_преподавателя": [{"карточка": n, "текст": redact(t, full_name)} for n, t in f.expert_comments],
    }


class FeedbackOut(BaseModel):
    """Ответ модели. Без жёстких пределов: лишнее обрезается, а не роняет черновик в запасной вариант."""

    summary: str
    progress: list[str] = []
    strengths: list[str] = []
    improve: list[str] = []
    next_step: str = ""


def _parts(out: FeedbackOut) -> DraftParts:
    def cut(items: list[str], n: int) -> list[str]:
        return [i.strip()[:400] for i in items if i.strip()][:n]

    return DraftParts(
        summary=out.summary.strip()[:600],
        progress=cut(out.progress, 3),
        strengths=cut(out.strengths, 2),
        improve=cut(out.improve, 3),
        next_step=out.next_step.strip()[:400],
    )


@dataclass(frozen=True, kw_only=True)
class DraftFeedback(Query):
    actor: Principal
    session_id: UUID
    student_id: UUID


@dataclass(frozen=True)
class FeedbackDraft:
    text: str
    source: str  # ai — модель, rules — правила (модели нет или она не ответила)
    model: str | None
    focus: list[dict[str, Any]]  # [{key, title, average}] — что предлагается подтянуть
    warnings: list[str]
    previous: dict[str, Any] | None  # прошлый отзыв этого преподавателя: {session_title, text, updated_at}


class DraftFeedbackHandler:
    def __init__(
        self, source: SessionFactsSource, repo: AssessmentRepository, store: FeedbackStore, router: ModelRouter
    ) -> None:
        self._source = source
        self._repo = repo
        self._store = store
        self._router = router

    async def __call__(self, q: DraftFeedback) -> FeedbackDraft:
        ctx = await feedback_context(
            self._source, self._repo, self._store, actor=q.actor, session_id=q.session_id, student_id=q.student_id
        )
        f = ctx.summary
        warnings = []
        if not f.cards:
            warnings.append("В этом занятии у обучающегося нет сохранённых карточек.")
        elif ctx.not_assessed:
            warnings.append(
                f"Не оценено карточек: {ctx.not_assessed}. Черновик учитывает только оценённые — "
                "нажмите «оценить все карточки»."
            )
        parts, source, model_id = rules_draft(f), "rules", None
        model = self._router.for_task(AITask.FEEDBACK_DRAFT)
        if model.provider_name != "fake" and f.assessed:
            try:
                result = await model.complete(
                    [
                        ChatMessage(
                            role="system",
                            content=load_prompt(AITask.FEEDBACK_DRAFT, model.profile.prompt_version),
                        ),
                        ChatMessage(
                            role="user", content=json.dumps(model_facts(f, ctx.person.full_name), ensure_ascii=False)
                        ),
                    ],
                    schema=FeedbackOut,
                )
                out = (
                    result.parsed
                    if isinstance(result.parsed, FeedbackOut)
                    else FeedbackOut.model_validate_json(result.text)
                )
                if out.summary.strip():
                    parts, source, model_id = _parts(out), "ai", model.model_id
            except (ExternalServiceError, ValueError) as e:
                log.warning("Черновик отзыва: модель недоступна, составлен по правилам: %s", e)
                warnings.append("Модель не ответила — черновик составлен по правилам.")
        prev = ctx.previous
        return FeedbackDraft(
            text=compose(parts),
            source=source,
            model=model_id,
            focus=[{"key": x.key, "title": x.title, "average": x.average} for x in f.focus],
            warnings=warnings,
            previous={"session_title": prev.session_title, "text": prev.text, "updated_at": prev.updated_at}
            if prev
            else None,
        )


@dataclass(frozen=True, kw_only=True)
class MyFeedback(Query):
    actor: Principal


@dataclass(frozen=True)
class FeedbackItem:
    session_id: UUID
    session_title: str
    text: str
    updated_at: datetime | None


class MyFeedbackHandler:
    """Отзывы преподавателей в истории обучающегося (п. 5.1): только свои."""

    def __init__(self, store: FeedbackStore) -> None:
        self._store = store

    async def __call__(self, q: MyFeedback) -> list[FeedbackItem]:
        return [
            FeedbackItem(session_id=r.session_id, session_title=r.session_title, text=r.text, updated_at=r.updated_at)
            for r in await self._store.for_student(q.actor.user_id)
        ]
