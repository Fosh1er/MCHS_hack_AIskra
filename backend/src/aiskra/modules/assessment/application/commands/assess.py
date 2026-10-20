"""Команда: оценить карточку 112 или работу ДДС по эталону (п. 3.4). Каждый запуск — новая версия оценки
(история сохраняется); результат — критерии, ошибки с пояснением, итог 0…100, «зачтено» по порогу."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from uuid import UUID, uuid4

from aiskra.modules.assessment.application.judge import Judge, JudgeOut
from aiskra.modules.assessment.application.ports.attempts import AssessmentRecord, AssessmentRepository, AttemptSource
from aiskra.modules.assessment.application.psy_judge import PsyJudge
from aiskra.modules.assessment.domain.branch_scoring import BranchAttempt, branch_details
from aiskra.modules.assessment.domain.psy_scoring import PsyAttempt, assess_psy, basis_of, timeline
from aiskra.modules.assessment.domain.scoring import (
    CARD_NORM_SECONDS,
    DDS_NORM_SECONDS,
    PASS_THRESHOLD,
    WEIGHTS_112,
    WEIGHTS_DDS,
    Criterion,
    Result,
    StatusStep,
    assess_card_112,
    assess_dds,
    finish,
)
from aiskra.shared.application import Command, UnitOfWork
from aiskra.shared.audit import AuditEntry, AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.errors import DomainError, NotFoundError
from aiskra.shared.security import Permission, Principal
from aiskra.shared.spelling import check_operator_text

RULE_PENALTY = 0.2  # грамотность без модели: −0,2 за каждое замечание правил


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


def _judge_criteria(out: JudgeOut | None, keys: list[str], texts: list[str] | None = None) -> list[Criterion]:
    """Критерии ИИ-судьи. Без модели смысл и регламентность — «не проверено», а грамотность проверяют правила
    (ТЗ 4.5, 5.10): повторы, латиница в русском слове, пробелы, скобки, частые орфографические ошибки."""
    crit = []
    for key in keys:
        score = getattr(out, key if key != "description_meaning" else "meaning", None) if out else None
        c = Criterion(key, score, note="" if out else "не проверено: ИИ-судья не подключён")
        if out and key == "grammar":
            c.errors = [f"«{r.quote}» → {r.fix}" for r in out.errors]
        elif key == "grammar" and texts is not None and any(t.strip() for t in texts):
            c = rules_grammar(texts)
        crit.append(c)
    return crit


def reaction_seconds(history: list[StatusStep], added_at: datetime | None) -> float | None:
    """Время реакции ДДС по карточке: от поступления в службу до решения (для отчёта по очереди, ТЗ 5.10)."""
    first = next((h for h in history if h.status not in ("added", "received")), None)
    if first is None or first.at is None or added_at is None:
        return None
    return round(max(0.0, (first.at - added_at).total_seconds()), 1)


def rules_grammar(texts: list[str]) -> Criterion:
    remarks = [r for t in texts for r in check_operator_text("текст", t)]
    c = Criterion(
        "grammar",
        round(max(0.0, 1 - RULE_PENALTY * len(remarks)), 3),
        note="проверено правилами (ИИ-судья не подключён)",
    )
    c.errors = [f"«{r.quote.strip() or r.quote}» → {r.fix} ({r.rule})" for r in remarks[:6]]
    return c


def psy_details(result: Result, attempt: PsyAttempt) -> dict[str, object]:
    """Блок «Работа с заявителем» в details оценки (п. 3.7)."""
    return {
        "score": result.score,
        "passed": result.passed,
        "weight": float(attempt.profile.get("weight") or 0),
        # F4: у критерия — «почему это важно» и источники
        "criteria": [{**asdict(c), "title": c.title, **basis_of(c.key)} for c in result.criteria],
        "errors": result.errors,
        "critical": [c.title for c in result.criteria if c.critical],
        "stats": result.stats,
        "timeline": timeline(attempt),
        "call_id": attempt.call_id,
    }


def combine(role_score: float, role_passed: bool, block: dict[str, object], threshold: float) -> tuple[float, bool]:
    """Итог с блоком при весе w > 0: (1 − w) × роль + w × блок; критическая ошибка блока — «не зачтено»."""
    w = float(block.get("weight") or 0)  # type: ignore[arg-type]
    if w <= 0:
        return role_score, role_passed
    score = round((1 - w) * role_score + w * float(block["score"]), 1)  # type: ignore[arg-type]
    return score, role_passed and score >= threshold and not block["critical"]


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
        self,
        attempts: AttemptSource,
        repo: AssessmentRepository,
        judge: Judge,
        audit: AuditRecorder,
        uow: UnitOfWork,
        psy_judge: PsyJudge | None = None,
    ) -> None:
        self._attempts = attempts
        self._repo = repo
        self._judge = judge
        self._audit = audit
        self._uow = uow
        self._psy_judge = psy_judge

    async def _psy_block(self, attempt: PsyAttempt | None, threshold: float) -> dict[str, object] | None:
        if attempt is None:
            return None
        if attempt.profile.get("paused"):
            return {"paused": True, "note": "звонок остановлен обучающимся — блок не оценивался", "stats": {}}
        judged = await self._psy_judge.check(attempt) if self._psy_judge else None
        return psy_details(assess_psy(attempt, judge=judged, threshold=threshold), attempt)

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
                criteria += _judge_criteria(
                    judged, ["description_meaning", "grammar"], [str(a.data.get("description") or "")]
                )
            weights = {**WEIGHTS_112, **s.weights}
            stats = {"processing_s": a.processing_s, "norm_s": s.norm_seconds or CARD_NORM_SECONDS}
            result = finish("112", criteria, weights, a.reference is not None, s.threshold, stats)
            student, number, service = a.author_id, a.card_number, None
            psy_attempt = a.psy
            branch_attempt: BranchAttempt | None = a.branch
        elif cmd.role == "dds":
            if not cmd.service_code:
                raise DomainError("Укажите службу ДДС", code="service_required")
            d = await self._attempts.dds(cmd.card_id, cmd.service_code)
            if d is None or (cmd.actor.user_id not in d.actor_ids and not teacher):
                raise NotFoundError("Работа ДДС по карточке не найдена", code="dds_attempt_not_found")
            criteria = assess_dds(
                d.history,
                d.added_at,
                d.reference,
                d.calls,
                norm_seconds=s.norm_seconds or DDS_NORM_SECONDS,
                call_log=d.call_log,
            )
            comments = [h.comment for h in d.history if h.comment]
            judged = await self._judge.check(legend="", description="", comments=comments) if comments else None
            criteria += _judge_criteria(judged, ["regulation", "grammar"], comments) if comments else []
            weights = {**WEIGHTS_DDS, **s.weights}
            # оценка — обучающемуся-ДДС: он сам или тот, кто ставил статусы (если запускает преподаватель)
            actor = cmd.actor.user_id if cmd.actor.user_id in d.actor_ids else next(iter(d.actor_ids), None)
            result = finish(
                "dds",
                criteria,
                weights,
                d.reference is not None,
                s.threshold,
                {"norm_s": s.norm_seconds or DDS_NORM_SECONDS, "reaction_s": reaction_seconds(d.history, d.added_at)},
            )
            student, number, service = actor, d.card_number, cmd.service_code
            psy_attempt = d.psy
            branch_attempt = None
        else:
            raise DomainError("Роль — 112 или dds", code="bad_role")

        details = to_details(result, service, number)
        score, passed = result.score, result.passed
        block = await self._psy_block(psy_attempt, s.threshold)
        if block is not None:
            details["psy"] = block
            if not block.get("paused"):
                details["role_score"] = result.score
                score, passed = combine(result.score, result.passed, block, s.threshold)
        if branch_attempt is not None:  # F5: «Развитие ситуации»; вес по умолчанию 0 — информативно
            branch = branch_details(branch_attempt)
            details["branch"] = branch
            if branch["final"] and float(branch["weight"]) > 0:
                details.setdefault("role_score", result.score)
                score, passed = combine(score, passed, branch, s.threshold)
        record = AssessmentRecord(
            id=uuid4(),
            card_id=cmd.card_id,
            student_id=student,
            role=result.role,
            service_code=service,
            score=score,
            passed=passed,
            grader="rules+llm" if judged else "rules",
            details=details,
        )
        prev = await self._repo.latest(cmd.card_id, result.role, service)
        if prev and prev.details.get("expert"):
            # экспертная оценка (п. 4.3) окончательна: повторная автопроверка обновляет критерии, но не балл
            expert = {**prev.details["expert"], "auto_score": score}
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
                    description=f"{'112' if result.role == '112' else 'ДДС ' + (service or '')}: {record.score} баллов"
                    + (" — зачтено" if record.passed else " — не зачтено")
                    + (f"; работа с заявителем: {block['score']}" if block and "score" in block else ""),
                    object_type="assessment",
                    object_id=str(record.id),
                )
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return record
