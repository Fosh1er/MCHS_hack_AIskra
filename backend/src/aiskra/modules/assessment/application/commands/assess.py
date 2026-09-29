"""Команда: оценить карточку 112 или работу ДДС по эталону (п. 3.4). Каждый запуск — новая версия оценки
(история сохраняется); результат — критерии, ошибки с пояснением, итог 0…100, «зачтено» по порогу."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from uuid import UUID, uuid4

from aiskra.modules.assessment.application.judge import Judge, JudgeOut
from aiskra.modules.assessment.application.ports.attempts import AssessmentRecord, AssessmentRepository, AttemptSource
from aiskra.modules.assessment.domain.scoring import (
    CARD_NORM_SECONDS,
    DDS_NORM_SECONDS,
    PASS_THRESHOLD,
    WEIGHTS_112,
    WEIGHTS_DDS,
    Criterion,
    Result,
    assess_card_112,
    assess_dds,
    finish,
)
from aiskra.shared.application import Command, UnitOfWork
from aiskra.shared.audit import AuditEntry, AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.errors import DomainError, NotFoundError
from aiskra.shared.security import Permission, Principal


@dataclass(frozen=True, kw_only=True)
class Settings:
    """Настраиваемые параметры оценки (ТЗ: критерии успешности, пороги, тайминг)."""

    weights: dict[str, float] = field(default_factory=dict)  # поверх значений по умолчанию
    norm_seconds: float | None = None
    threshold: float = PASS_THRESHOLD


@dataclass(frozen=True, kw_only=True)
class AssessCard(Command):
    actor: Principal
    card_id: UUID
    role: str  # 112 | dds
    service_code: str | None = None
    settings: Settings = field(default_factory=Settings)
    meta: RequestMeta = field(default_factory=RequestMeta)


def _judge_criteria(out: JudgeOut | None, keys: list[str]) -> list[Criterion]:
    crit = []
    for key in keys:
        score = getattr(out, key if key != "description_meaning" else "meaning", None) if out else None
        c = Criterion(key, score, note="" if out else "не проверено: ИИ-судья не подключён")
        if out and key == "grammar":
            c.errors = [f"«{r.quote}» → {r.fix}" for r in out.errors]
        crit.append(c)
    return crit


def to_details(result: Result, service_code: str | None, card_number: int) -> dict[str, object]:
    return {
        "role": result.role,
        "service_code": service_code,
        "card_number": card_number,
        "has_reference": result.has_reference,
        "criteria": [{**asdict(c), "title": c.title} for c in result.criteria],
        "errors": result.errors,
        "critical": [c.title for c in result.criteria if c.critical],  # п. 3.5: «не зачтено» при любом балле
        "stats": result.stats,
    }


class AssessCardHandler:
    def __init__(
        self, attempts: AttemptSource, repo: AssessmentRepository, judge: Judge, audit: AuditRecorder, uow: UnitOfWork
    ) -> None:
        self._attempts = attempts
        self._repo = repo
        self._judge = judge
        self._audit = audit
        self._uow = uow

    async def __call__(self, cmd: AssessCard) -> AssessmentRecord:
        teacher = cmd.actor.can(Permission.RESULTS_READ_ALL)
        s = cmd.settings
        if cmd.role == "112":
            a = await self._attempts.card_112(cmd.card_id)
            if a is None or (a.author_id != cmd.actor.user_id and not teacher):
                raise NotFoundError("Карточка не найдена", code="card_not_found")
            if a.status == "draft":
                raise DomainError("Карточка ещё не сохранена", code="card_not_saved")
            criteria = assess_card_112(
                a.data,
                a.services,
                a.processing_s,
                a.reference,
                a.asked_topics,
                norm_seconds=s.norm_seconds or CARD_NORM_SECONDS,
                names=a.service_names,
                flag_names=a.flag_names,
                spoken=a.legend_text or None,
                caller=a.caller,
            )
            judged = (
                await self._judge.check(
                    legend=a.legend_text, description=str(a.data.get("description") or ""), comments=[]
                )
                if a.reference
                else None
            )
            if a.reference:
                criteria += _judge_criteria(judged, ["description_meaning", "grammar"])
            weights = {**WEIGHTS_112, **s.weights}
            stats = {"processing_s": a.processing_s, "norm_s": s.norm_seconds or CARD_NORM_SECONDS}
            result = finish("112", criteria, weights, a.reference is not None, s.threshold, stats)
            student, number, service = a.author_id, a.card_number, None
        elif cmd.role == "dds":
            if not cmd.service_code:
                raise DomainError("Укажите службу ДДС", code="service_required")
            d = await self._attempts.dds(cmd.card_id, cmd.service_code)
            if d is None or (cmd.actor.user_id not in d.actor_ids and not teacher):
                raise NotFoundError("Работа ДДС по карточке не найдена", code="dds_attempt_not_found")
            criteria = assess_dds(
                d.history, d.added_at, d.reference, d.calls, norm_seconds=s.norm_seconds or DDS_NORM_SECONDS
            )
            comments = [h.comment for h in d.history if h.comment]
            judged = await self._judge.check(legend="", description="", comments=comments) if comments else None
            criteria += _judge_criteria(judged, ["regulation", "grammar"]) if comments else []
            weights = {**WEIGHTS_DDS, **s.weights}
            # оценка — обучающемуся-ДДС: он сам или тот, кто ставил статусы (если запускает преподаватель)
            actor = cmd.actor.user_id if cmd.actor.user_id in d.actor_ids else next(iter(d.actor_ids), None)
            result = finish(
                "dds",
                criteria,
                weights,
                d.reference is not None,
                s.threshold,
                {"norm_s": s.norm_seconds or DDS_NORM_SECONDS},
            )
            student, number, service = actor, d.card_number, cmd.service_code
        else:
            raise DomainError("Роль — 112 или dds", code="bad_role")

        record = AssessmentRecord(
            id=uuid4(),
            card_id=cmd.card_id,
            student_id=student,
            role=result.role,
            service_code=service,
            score=result.score,
            passed=result.passed,
            grader="rules+llm" if judged else "rules",
            details=to_details(result, service, number),
        )
        prev = await self._repo.latest(cmd.card_id, result.role, service)
        if prev and prev.details.get("expert"):
            # экспертная оценка (п. 4.3) окончательна: повторная автопроверка обновляет критерии, но не балл
            expert = {**prev.details["expert"], "auto_score": result.score}
            record = replace(
                record,
                score=float(expert["score"]),
                passed=bool(prev.passed),
                grader="expert",
                details={**record.details, "expert": expert},
            )
        try:
            await self._repo.add(record)
            await self._audit.record(
                AuditEntry(
                    event=AuditEvent.CARD_ASSESSED,
                    actor=cmd.actor,
                    card_number=number,
                    meta=cmd.meta,
                    description=f"{'112' if result.role == '112' else 'ДДС ' + (service or '')}: {result.score} баллов"
                    + (" — зачтено" if result.passed else " — не зачтено"),
                    object_type="assessment",
                    object_id=str(record.id),
                )
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return record
