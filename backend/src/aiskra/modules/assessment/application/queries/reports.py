"""Отчёт по занятию и прогресс обучающегося (п. 4.3).

ТЗ, сценарии 2–3: действия, замечания (ошибки), время заполнения карточки, отклонение от нормативного, грамматика.
Диаграммы (ТЗ «объективность диаграмм»): тепловая карта «обучающийся × критерий» (средний балл критерия),
распределение времени заполнения, динамика баллов. Данные диаграмм — те же числа, что в таблицах.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from aiskra.modules.assessment.application.ports.attempts import AssessmentRecord, AssessmentRepository
from aiskra.modules.assessment.application.ports.reports import (
    ReportCard,
    ReportParticipant,
    SessionFacts,
    SessionFactsSource,
)
from aiskra.modules.assessment.domain.recommendations import recommend
from aiskra.modules.assessment.domain.scoring import CARD_NORM_SECONDS, DDS_NORM_SECONDS, TITLES
from aiskra.shared.application import Query
from aiskra.shared.errors import NotFoundError
from aiskra.shared.security import Principal

TIME_BUCKETS = [
    (0, 40, "до 40 с"),
    (40, 75, "40–75 с"),
    (75, 120, "75–120 с"),
    (120, 180, "2–3 мин"),
    (180, 10**9, "больше 3 мин"),
]


# Как оператор вёл разговор с заявителем (п. 3.6): в голосовом режиме во время карточки входит речь собеседника
CALL_MODE_TITLES = {"text": "текстом", "voice": "голосом", "hands_free": "голосом без рук"}


@dataclass(frozen=True)
class CardResult:
    card_id: UUID
    card_number: int
    card_types: list[str]
    processing_s: float | None
    norm_s: float
    deviation_s: float | None  # + — дольше норматива
    assessment_id: UUID | None
    score: float | None
    passed: bool | None
    expert: bool
    expert_comment: str
    errors: list[str]
    criteria: dict[str, float | None]
    call_mode: str | None = None  # text | voice | hands_free: в голосовом режиме во время входит речь собеседника


@dataclass(frozen=True)
class StudentReport:
    student_id: UUID
    full_name: str
    role: str
    service_code: str | None
    cards: list[CardResult]
    avg_score: float | None
    passed_share: float | None
    avg_time_s: float | None
    not_assessed: int


@dataclass(frozen=True)
class Heatmap:
    criteria: list[dict[str, str]]  # [{key, title}]
    rows: list[dict[str, Any]]  # [{student, role, values: {key: 0..1 | None}}]


@dataclass(frozen=True)
class SessionReport:
    session_id: UUID
    title: str
    mode: str
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    settings: dict[str, Any]
    students: list[StudentReport]
    avg_score: float | None
    passed_share: float | None
    cards_count: int
    heatmap: Heatmap
    time_buckets: list[dict[str, Any]] = field(default_factory=list)
    score_series: list[dict[str, Any]] = field(default_factory=list)


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def _result(card: ReportCard, rec: AssessmentRecord | None, norm: float, role: str) -> CardResult:
    processing = card.processing_s if role == "112" else None
    return CardResult(
        card_id=card.card_id,
        card_number=card.number,
        card_types=card.card_types,
        processing_s=processing,
        norm_s=norm,
        deviation_s=round(processing - norm, 1) if processing is not None else None,
        assessment_id=rec.id if rec else None,
        score=rec.score if rec else None,
        passed=rec.passed if rec else None,
        expert=bool(rec and rec.details.get("expert")),
        expert_comment=str((rec.details.get("expert") or {}).get("comment", "")) if rec else "",
        errors=list(rec.details.get("errors", [])) if rec else [],
        criteria={c["key"]: c.get("score") for c in rec.details.get("criteria", [])} if rec else {},
        call_mode=card.call_mode if role == "112" else None,
    )


def cards_of(p: ReportParticipant, cards: list[ReportCard]) -> list[ReportCard]:
    """Карточки участника: свои сохранённые карточки 112 или карточки занятия, поступившие в его ДДС."""
    if p.role == "112":
        return [c for c in cards if c.author_id == p.student_id and c.status != "draft" and c.origin != "system"]
    return [c for c in cards if p.service_code in c.services and c.status != "draft"]


@dataclass(frozen=True, kw_only=True)
class GetSessionReport(Query):
    actor: Principal
    session_id: UUID


class GetSessionReportHandler:
    def __init__(self, source: SessionFactsSource, repo: AssessmentRepository) -> None:
        self._source = source
        self._repo = repo

    async def __call__(self, q: GetSessionReport) -> SessionReport:
        facts = await self._source.session(q.session_id)
        if facts is None or facts.teacher_id != q.actor.user_id:
            raise NotFoundError("Занятие не найдено", code="session_not_found")
        return await build_report(facts, self._repo)


async def build_report(facts: SessionFacts, repo: AssessmentRepository, only: UUID | None = None) -> SessionReport:
    """Отчёт по фактам занятия; `only` — только этот обучающийся (его кабинет, п. 5.1)."""
    norm112 = float(facts.settings.get("norm_112", CARD_NORM_SECONDS))
    norm_dds = float(facts.settings.get("norm_dds", DDS_NORM_SECONDS))
    students, heat_rows, all_scores, all_passed, times, series = [], [], [], [], [], []
    keys: dict[str, str] = {}
    for p in [x for x in facts.participants if only is None or x.student_id == only]:
        results = []
        for card in cards_of(p, facts.cards):
            rec = await repo.latest(card.card_id, p.role, p.service_code if p.role == "dds" else None)
            results.append(_result(card, rec, norm112 if p.role == "112" else norm_dds, p.role))
            if rec:
                series.append(
                    {"t": card.saved_at.isoformat() if card.saved_at else "", "v": rec.score, "who": p.full_name}
                )
        scores = [r.score for r in results if r.score is not None]
        passed = [bool(r.passed) for r in results if r.passed is not None]
        ptimes = [r.processing_s for r in results if r.processing_s is not None]
        all_scores += scores
        all_passed += passed
        times += ptimes
        per_key: dict[str, list[float]] = defaultdict(list)
        for r in results:
            for k, v in r.criteria.items():
                keys.setdefault(k, TITLES.get(k, k))
                if v is not None:
                    per_key[k].append(float(v))
        heat_rows.append(
            {
                "student": p.full_name,
                "role": p.role,
                "values": {k: round(sum(v) / len(v), 2) for k, v in per_key.items()},
            }
        )
        students.append(
            StudentReport(
                student_id=p.student_id,
                full_name=p.full_name,
                role=p.role,
                service_code=p.service_code,
                cards=results,
                avg_score=_avg(scores),
                passed_share=round(sum(passed) / len(passed), 3) if passed else None,
                avg_time_s=_avg(ptimes),
                not_assessed=sum(1 for r in results if r.score is None),
            )
        )
    buckets = [{"label": label, "count": sum(1 for t in times if lo <= t < hi)} for lo, hi, label in TIME_BUCKETS]
    return SessionReport(
        session_id=facts.session_id,
        title=facts.title,
        mode=facts.mode,
        status=facts.status,
        started_at=facts.started_at,
        finished_at=facts.finished_at,
        settings=facts.settings,
        students=students,
        avg_score=_avg(all_scores),
        passed_share=round(sum(all_passed) / len(all_passed), 3) if all_passed else None,
        cards_count=sum(len(s.cards) for s in students),
        heatmap=Heatmap(criteria=[{"key": k, "title": t} for k, t in keys.items()], rows=heat_rows),
        time_buckets=buckets,
        score_series=sorted(series, key=lambda x: x["t"]),
    )


def report_csv(r: SessionReport) -> str:
    """CSV для Excel: разделитель «;», BOM — чтобы кириллица открылась без мастера импорта."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    share = f"{round(r.passed_share * 100)} %" if r.passed_share is not None else ""
    w.writerow(["Занятие", r.title, "Средний балл", r.avg_score, "Зачтено", share])
    w.writerow([])
    w.writerow(
        [
            "ФИО",
            "Роль",
            "Служба",
            "Карточка",
            "Тип",
            "Время, с",
            "Норматив, с",
            "Отклонение, с",
            "Разговор",
            "Балл",
            "Зачтено",
            "Экспертная правка",
            "Комментарий эксперта",
            "Замечания",
        ]
    )
    for s in r.students:
        for c in s.cards:
            w.writerow(
                [
                    s.full_name,
                    "оператор 112" if s.role == "112" else "ДДС",
                    s.service_code or "",
                    c.card_number,
                    ", ".join(c.card_types),
                    c.processing_s if c.processing_s is not None else "",
                    c.norm_s,
                    c.deviation_s if c.deviation_s is not None else "",
                    CALL_MODE_TITLES.get(c.call_mode or "", ""),
                    c.score if c.score is not None else "не оценена",
                    "" if c.passed is None else ("да" if c.passed else "нет"),
                    "да" if c.expert else "",
                    c.expert_comment,
                    " | ".join(c.errors),
                ]
            )
    return "﻿" + buf.getvalue()


@dataclass(frozen=True, kw_only=True)
class MyProgress(Query):
    actor: Principal
    limit: int = 100


@dataclass(frozen=True)
class ProgressView:
    points: list[dict[str, Any]]  # [{t, v, role, card_number, passed}]
    avg_score: float | None
    weakest: list[dict[str, Any]]  # [{key, title, average}]
    recent_errors: list[str]
    expert_comments: list[dict[str, Any]] = field(default_factory=list)  # [{card_number, score, comment}]
    recommendations: list[dict[str, Any]] = field(default_factory=list)  # [{key, average, text}]


class MyProgressHandler:
    def __init__(self, repo: AssessmentRepository) -> None:
        self._repo = repo

    async def __call__(self, q: MyProgress) -> ProgressView:
        records = [r for r in await self._repo.recent(q.limit * 5) if r.student_id == q.actor.user_id][: q.limit]
        latest: dict[tuple[UUID, str, str | None], AssessmentRecord] = {}
        for r in records:  # recent — от новых к старым: берём последнюю версию оценки карточки
            latest.setdefault((r.card_id, r.role, r.service_code), r)
        ordered = sorted(latest.values(), key=lambda r: r.created_at or datetime.min.replace(tzinfo=UTC))
        per_key: dict[str, list[float]] = defaultdict(list)
        for r in ordered:
            for c in r.details.get("criteria", []):
                if c.get("score") is not None:
                    per_key[c["key"]].append(float(c["score"]))
        averages = sorted((round(sum(v) / len(v), 2), k) for k, v in per_key.items())[:4]
        weakest: list[dict[str, Any]] = [{"key": k, "title": TITLES.get(k, k), "average": a} for a, k in averages]
        recs = recommend({k: sum(v) / len(v) for k, v in per_key.items()})
        return ProgressView(
            recommendations=recs,
            points=[
                {
                    "t": r.created_at.isoformat() if r.created_at else "",
                    "v": r.score,
                    "role": r.role,
                    "card_number": r.details.get("card_number"),
                    "passed": r.passed,
                }
                for r in ordered
            ],
            avg_score=_avg([r.score for r in ordered]),
            weakest=weakest,
            recent_errors=[e for r in reversed(ordered[-3:]) for e in r.details.get("errors", [])][:6],
            expert_comments=[
                {
                    "card_number": r.details.get("card_number"),
                    "score": r.score,
                    "comment": r.details["expert"]["comment"],
                }
                for r in reversed(ordered)
                if r.details.get("expert")
            ][:5],
        )


@dataclass(frozen=True, kw_only=True)
class GetMySessionReport(Query):
    actor: Principal
    session_id: UUID


@dataclass(frozen=True)
class MySessionReport:
    report: SessionReport
    recommendations: list[dict[str, Any]]


class GetMySessionReportHandler:
    """Свои результаты по занятию (п. 5.1): только участнику и только его карточки."""

    def __init__(self, source: SessionFactsSource, repo: AssessmentRepository) -> None:
        self._source = source
        self._repo = repo

    async def __call__(self, q: GetMySessionReport) -> MySessionReport:
        facts = await self._source.session(q.session_id)
        if facts is None or all(p.student_id != q.actor.user_id for p in facts.participants):
            raise NotFoundError("Занятие не найдено", code="session_not_found")
        report = await build_report(facts, self._repo, only=q.actor.user_id)
        row = report.heatmap.rows[0]["values"] if report.heatmap.rows else {}
        return MySessionReport(report=report, recommendations=recommend(row))
