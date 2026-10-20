"""Команды сценариев (п. 3.2): генерация банка, утверждение, архив.

Генерация: строка классификатора (по выбранным группам) → случайный дом из адресного справочника → службы по
правилам классификатора (1.5) → модель пишет «своими словами» описание и первую реплику (`scenario_generation`,
структурированный ответ). Без модели — шаблоны `offline_story`. Эталон собирается правилами, не моделью."""

from __future__ import annotations

import json
import logging
import random
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from aiskra.ai.ports import ChatMessage
from aiskra.ai.prompts import load_prompt
from aiskra.ai.router import ModelRouter
from aiskra.ai.tasks import AITask
from aiskra.modules.training.application.ports.branching import BranchCatalog
from aiskra.modules.training.application.ports.materials import MaterialContext
from aiskra.modules.training.application.ports.psy import PsyCatalog
from aiskra.modules.training.application.ports.scenarios import ScenarioFactsSource, ScenarioRepository
from aiskra.modules.training.domain.actors import ANSWER_TOPICS, answer_fact_errors
from aiskra.modules.training.domain.branching import Template, apply_texts, event_nodes
from aiskra.modules.training.domain.review import accept_all
from aiskra.modules.training.domain.scenario import FLAG_FACTS, Scenario, ScenarioStatus, build_scenario, offline_story
from aiskra.modules.training.domain.spelling import Remark, check_legend
from aiskra.shared.application import Command, UnitOfWork
from aiskra.shared.audit import AuditEntry, AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.errors import DomainError, ExternalServiceError, NotFoundError
from aiskra.shared.security import Principal

log = logging.getLogger(__name__)
MAX_BATCH = 50


class BranchTextsOut(BaseModel):
    """Ответ модели для F5: реплики-события узлов под легенду, ключ — id узла."""

    texts: dict[str, str] = Field(default_factory=dict)


_DIGITS = re.compile(r"\d+")


def check_event_text(text: str, original: str, legend: Mapping[str, object]) -> str | None:
    """Факты в реплике-событии модели: только из исходной реплики и легенды (как в 3.2). Причина отказа или None."""
    t = text.strip()
    if not 3 <= len(t) <= 200:
        return "длина"
    if "[" in t or "]" in t:
        return "ремарки"
    known = set(_DIGITS.findall(original)) | set(_DIGITS.findall(json.dumps(legend, ensure_ascii=False)))
    if set(_DIGITS.findall(t)) - known:
        return "новые числа"
    if re.search(r"\b(10[1-4]|112|0[1-4])\b", t) and not re.search(r"\b(10[1-4]|112|0[1-4])\b", original):
        return "номера служб"
    return None


def with_template(scenario: Scenario, tpl: Template, snapshot: dict[str, object]) -> Scenario:
    """F5: легенда и эталон согласуются с шаблоном (пострадавшие, статус заявителя, первые фразы), сценарию —
    копия шаблона. Узлы рассчитаны на эту ситуацию, поэтому её тексты берутся из шаблона, а не у модели."""
    legend = dict(scenario.legend)
    for key, value in tpl.legend.items():
        legend[key] = (
            {**legend[key], **value} if isinstance(value, dict) and isinstance(legend.get(key), dict) else value
        )
    reference = dict(scenario.reference_card)
    if "victims" in tpl.legend:
        reference["victims"] = dict(legend["victims"])
    status = (tpl.legend.get("applicant") or {}).get("status")
    if status:
        reference["applicant"] = {**(reference.get("applicant") or {}), "status": status}
    scenario.legend = legend
    scenario.reference_card = reference
    scenario.branching = snapshot
    return scenario


class StoryOut(BaseModel):
    """Ответ модели: только естественный язык."""

    description: str = Field(max_length=600, description="Что видит заявитель, 1–3 предложения")
    opening: str = Field(max_length=300, description="Первая фраза заявителя")
    details: str = Field(default="", max_length=400, description="Детали, если расспросить")


@dataclass(frozen=True, kw_only=True)
class GenerateScenarios(Command):
    actor: Principal | None
    count: int = 1
    groups: list[int] = field(default_factory=list)  # группы классификатора; пусто — любые
    difficulty: int = 2
    approve: bool = False  # сразу в банк (CLI-заготовка демо); по умолчанию — на проверку преподавателю
    seed: int | None = None
    branching: str | None = None  # F5: шаблон ветвления; None — сценарий без ветвления
    codes: list[str] = field(default_factory=list)  # строки классификатора; пусто — любые строки групп
    flags: list[str] | None = None  # признаки опросной карты; None — случайно из признаков строки
    meta: RequestMeta = field(default_factory=RequestMeta)


class ScenarioGenerator:
    """Одна генерация без сохранения — используется и командой, и входящим вызовом при пустом банке."""

    def __init__(
        self,
        facts: ScenarioFactsSource,
        router: ModelRouter,
        materials: MaterialContext | None = None,
        branches: BranchCatalog | None = None,
    ) -> None:
        self._facts = facts
        self._router = router
        self._materials = materials
        self._branches = branches

    async def _event_texts(self, snapshot: dict[str, object], legend: dict[str, object]) -> dict[str, str]:
        """RF5-09: модель переписывает только реплики-события под легенду; структура, условия и итоги — из шаблона.
        Реплика с новыми фактами (числа, номера служб) отклоняется — остаётся текст шаблона."""
        model = self._router.for_task(AITask.BRANCH_TEXTS)
        events = event_nodes(snapshot)
        if model.provider_name == "fake" or not events:
            return {}
        public: dict[str, object] = {k: legend[k] for k in ("what", "details", "applicant", "victims") if k in legend}
        try:
            result = await model.complete(
                [
                    ChatMessage(role="system", content=load_prompt(AITask.BRANCH_TEXTS)),
                    ChatMessage(
                        role="user", content=json.dumps({"легенда": public, "реплики": events}, ensure_ascii=False)
                    ),
                ],
                schema=BranchTextsOut,
            )
            out = (
                result.parsed
                if isinstance(result.parsed, BranchTextsOut)
                else BranchTextsOut.model_validate_json(result.text)
            )
        except (ExternalServiceError, ValueError) as e:
            log.warning("Реплики ветвления моделью не получились, текст шаблона: %s", e)
            return {}
        return {
            nid: text.strip()
            for nid, text in out.texts.items()
            if nid in events and check_event_text(text, events[nid], public) is None
        }

    async def _with_materials(self, facts: dict[str, object]) -> dict[str, object]:
        """R4.4-06: выдержки из материалов «для генерации» по типу и признакам — модель согласует с ними легенду."""
        if self._materials is None:
            return facts
        signs = facts.get("признаки")
        parts = [facts.get("тип"), *(signs if isinstance(signs, list) else [])]
        query = " ".join(str(x) for x in parts if x)
        found = await self._materials.snippets(query, limit=3)
        if not found:
            return facts
        return {**facts, "выдержки_из_учебных_материалов": [f"{t}: {p}" for t, p in found]}

    async def _story(
        self, incident_facts: Mapping[str, object], fallback: dict[str, str]
    ) -> tuple[dict[str, str], str]:
        model = self._router.for_task(AITask.SCENARIO_GENERATION)
        if model.provider_name == "fake":
            return fallback, "offline"
        incident_facts = await self._with_materials(dict(incident_facts))
        try:
            result = await model.complete(
                [
                    ChatMessage(role="system", content=load_prompt(AITask.SCENARIO_GENERATION)),
                    ChatMessage(role="user", content=json.dumps(incident_facts, ensure_ascii=False)),
                ],
                schema=StoryOut,
            )
            story = result.parsed if isinstance(result.parsed, StoryOut) else StoryOut.model_validate_json(result.text)
            return story.model_dump(), "ai"
        except (ExternalServiceError, ValueError) as e:
            log.warning("Генерация легенды моделью не удалась, шаблон: %s", e)
            return fallback, "offline"

    async def generate(
        self,
        rng: random.Random,
        groups: list[int],
        difficulty: int,
        author: UUID | None,
        branching: str | None = None,
        codes: list[str] | None = None,
        forced_flags: list[str] | None = None,
    ) -> Scenario:
        tpl = self._branches.get(branching) if branching and self._branches else None
        if branching and tpl is None:
            raise DomainError("Нет такого шаблона ветвления", code="bad_branching")
        incident = await self._facts.pick_incident(
            rng, groups or None, list(tpl.incident_codes) if tpl else (codes or None)
        )
        address = await self._facts.pick_address(rng)
        flags = [f for f in incident.flags if f in FLAG_FACTS and rng.random() < 0.5]
        if forced_flags is not None:  # засев стенда: признаки заданы — эталон служб предсказуем (нужная ДДС в нём)
            flags = [f for f in incident.flags if f in FLAG_FACTS and f in forced_flags]
        if tpl is not None:  # F5: признаки — по легенде шаблона, а не случайно (иначе эталон разойдётся с ситуацией)
            victims = bool((tpl.legend.get("victims") or {}).get("has"))
            flags = [f for f in incident.flags if f == "victims" and victims]
        services = await self._facts.resolve_services(incident.code, flags, address.okrug, address.district)
        fallback = offline_story(incident, address, flags, difficulty)
        facts = {
            "тип": incident.final_type,
            "признаки": [incident.sign1, incident.sign2, incident.sign3],
            "адрес": address.label,
            "район": address.district_name,
            "признаки_опросной_карты": [FLAG_FACTS[f][1] for f in flags],
            "сложность": difficulty,
        }
        # F5: у ветвящегося сценария первые фразы и описание — из шаблона (узлы рассчитаны на эту ситуацию)
        story, source = (fallback, "offline") if tpl else await self._story(facts, fallback)
        scenario = build_scenario(
            incident=incident,
            address=address,
            services=services,
            story=story,
            flags=flags,
            difficulty=difficulty,
            rng=rng,
            source="ai" if source == "ai" else "template",
            author_id=author,
        )
        if tpl is not None and self._branches is not None:
            snapshot = self._branches.snapshot(tpl.id, scenario.legend)
            scenario = with_template(scenario, tpl, snapshot)
            texts = await self._event_texts(snapshot, scenario.legend)
            scenario.branching = apply_texts(snapshot, texts) if texts else snapshot
        return scenario


class GenerateScenariosHandler:
    def __init__(
        self, generator: ScenarioGenerator, repo: ScenarioRepository, audit: AuditRecorder, uow: UnitOfWork
    ) -> None:
        self._gen = generator
        self._repo = repo
        self._audit = audit
        self._uow = uow

    async def __call__(self, cmd: GenerateScenarios) -> list[UUID]:
        if not 1 <= cmd.count <= MAX_BATCH:
            raise DomainError(f"За раз — от 1 до {MAX_BATCH} сценариев", code="bad_count")
        rng = random.Random(cmd.seed)
        author = cmd.actor.user_id if cmd.actor else None
        ids: list[UUID] = []
        try:
            for _ in range(cmd.count):
                scenario = await self._gen.generate(
                    rng, cmd.groups, cmd.difficulty, author, cmd.branching, cmd.codes, cmd.flags
                )
                if cmd.approve:  # из CLI — от имени системы
                    scenario.status = ScenarioStatus.APPROVED
                    scenario.approved_by = author
                await self._repo.add(scenario)
                ids.append(scenario.id)
            await self._audit.record(
                AuditEntry(
                    event=AuditEvent.SCENARIOS_GENERATED,
                    actor=cmd.actor,
                    meta=cmd.meta,
                    description=f"Сгенерировано сценариев: {len(ids)}, сложность {cmd.difficulty}",
                    data={"groups": cmd.groups, "count": len(ids), "branching": cmd.branching},
                )
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return ids


@dataclass(frozen=True, kw_only=True)
class ReviewScenario(Command):
    actor: Principal
    scenario_id: UUID
    approve: bool  # True — утвердить (в банк занятий), False — в архив
    meta: RequestMeta = field(default_factory=RequestMeta)


class ReviewScenarioHandler:
    def __init__(self, repo: ScenarioRepository, audit: AuditRecorder, uow: UnitOfWork) -> None:
        self._repo = repo
        self._audit = audit
        self._uow = uow

    async def __call__(self, cmd: ReviewScenario) -> str:
        scenario = await self._repo.get(cmd.scenario_id)
        if scenario is None:
            raise NotFoundError("Сценарий не найден", code="scenario_not_found")
        if cmd.approve:  # полное утверждение — все разделы эталона приняты (п. 3.3)
            accept_all(scenario, by=str(cmd.actor.user_id))
            scenario.approve(cmd.actor.user_id)
        else:
            scenario.archive()
        try:
            await self._repo.save(scenario)
            await self._audit.record(
                AuditEntry(
                    event=AuditEvent.SCENARIO_APPROVED if cmd.approve else AuditEvent.SCENARIO_ARCHIVED,
                    actor=cmd.actor,
                    meta=cmd.meta,
                    description=scenario.title,
                    object_type="scenario",
                    object_id=str(scenario.id),
                )
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return scenario.status.value


@dataclass(frozen=True, kw_only=True)
class EditScenario(Command):
    """Правка преподавателем (ТЗ: «коррекция» и «проверка грамматики после ручных правок» — правка возвращает
    сценарий в черновик, чтобы его снова утвердили)."""

    actor: Principal
    scenario_id: UUID
    title: str | None = None
    difficulty: int | None = None
    opening: str | None = None
    what: str | None = None
    details: str | None = None
    comment: str | None = None  # комментарий для перегенерации речи заявителя моделью
    meta: RequestMeta = field(default_factory=RequestMeta)


class GrammarRemarkOut(BaseModel):
    quote: str = Field(max_length=200)
    fix: str = Field(max_length=200)


class GrammarOut(BaseModel):
    errors: list[GrammarRemarkOut] = Field(default_factory=list, max_length=8)


GRAMMAR_PROMPT = (
    "Ты корректор русского языка. Найди орфографические, пунктуационные и грамматические ошибки в тексте легенды "
    'учебного вызова 112 (разговорная речь заявителя допустима). Верни JSON {"errors": [{"quote": фрагмент с '
    'ошибкой, "fix": исправление}]}; ошибок нет — пустой список.'
)


@dataclass(frozen=True)
class EditResult:
    status: str
    grammar: list[Remark]
    checked_by: str  # rules | rules+model


class EditScenarioHandler:
    def __init__(self, repo: ScenarioRepository, router: ModelRouter, audit: AuditRecorder, uow: UnitOfWork) -> None:
        self._repo = repo
        self._router = router
        self._audit = audit
        self._uow = uow

    async def _regenerate(self, s: Scenario, comment: str) -> None:
        model = self._router.for_task(AITask.SCENARIO_GENERATION)
        if model.provider_name == "fake":
            raise DomainError(
                "Перегенерация по комментарию требует подключённой модели (config/ai.yaml)", code="ai_unavailable"
            )
        facts = {
            "тип": s.reference_card.get("final_type"),
            "признаки": list((s.reference_card.get("questionnaire") or {}).get(s.card_type_code, {}).values()),
            "адрес": (s.legend.get("address") or {}).get("label"),
            "признаки_опросной_карты": list((s.legend.get("facts") or {}).values()),
            "сложность": s.difficulty,
            "текущая_легенда": {k: s.legend.get(k) for k in ("what", "opening", "details")},
            "комментарий_преподавателя": comment,
        }
        try:
            result = await model.complete(
                [
                    ChatMessage(role="system", content=load_prompt(AITask.SCENARIO_GENERATION)),
                    ChatMessage(role="user", content=json.dumps(facts, ensure_ascii=False)),
                ],
                schema=StoryOut,
            )
        except ExternalServiceError as e:
            raise DomainError(f"Модель недоступна: {e}", code="ai_unavailable") from e
        story = result.parsed if isinstance(result.parsed, StoryOut) else StoryOut.model_validate_json(result.text)
        s.legend.update(what=story.description, opening=story.opening, details=story.details)

    async def __call__(self, cmd: EditScenario) -> EditResult:
        s = await self._repo.get(cmd.scenario_id)
        if s is None:
            raise NotFoundError("Сценарий не найден", code="scenario_not_found")
        if cmd.title is not None:
            if not cmd.title.strip():
                raise DomainError("Название не может быть пустым", code="empty_title")
            s.title = cmd.title.strip()[:255]
        if cmd.difficulty is not None:
            if not 1 <= cmd.difficulty <= 5:
                raise DomainError("Сложность — от 1 до 5", code="bad_difficulty")
            s.difficulty = cmd.difficulty
            s.legend["difficulty"] = cmd.difficulty
        for key in ("opening", "what", "details"):
            value = getattr(cmd, key)
            if value is not None:
                s.legend[key] = " ".join(value.split())[:600]
        if cmd.comment and cmd.comment.strip():
            await self._regenerate(s, cmd.comment.strip())
        remarks, by = await self._check_grammar(s)
        s.legend["grammar_check"] = {
            "at": datetime.now(UTC).isoformat(),
            "by": by,
            "remarks": [asdict(r) for r in remarks],
        }
        s.status = ScenarioStatus.DRAFT
        s.approved_by = None
        try:
            await self._repo.save(s)
            await self._audit.record(
                AuditEntry(
                    event=AuditEvent.SCENARIO_EDITED,
                    actor=cmd.actor,
                    meta=cmd.meta,
                    description=s.title,
                    object_type="scenario",
                    object_id=str(s.id),
                )
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return EditResult(status=s.status.value, grammar=remarks, checked_by=by)

    async def _check_grammar(self, s: Scenario, fields: dict[str, str] | None = None) -> tuple[list[Remark], str]:
        """П. 3.6: после каждой ручной правки — правила всегда, модель — если подключена (сбой модели не мешает)."""
        if fields is None:
            fields = {"title": s.title, **{k: str(s.legend.get(k) or "") for k in ("opening", "what", "details")}}
        remarks = check_legend(fields)
        model = self._router.for_task(AITask.JUDGE)
        if model.provider_name == "fake":
            return remarks, "rules"
        text = "\n".join(f"{k}: {v}" for k, v in fields.items() if v)
        try:
            result = await model.complete(
                [ChatMessage(role="system", content=GRAMMAR_PROMPT), ChatMessage(role="user", content=text)],
                schema=GrammarOut,
            )
            out = (
                result.parsed if isinstance(result.parsed, GrammarOut) else GrammarOut.model_validate_json(result.text)
            )
        except Exception:
            logging.getLogger(__name__).warning("проверка грамотности моделью не выполнена", exc_info=True)
            return remarks, "rules"
        seen = {r.quote for r in remarks}
        remarks += [Remark("текст", e.quote, e.fix, "ИИ-проверка") for e in out.errors if e.quote not in seen]
        return remarks, "rules+model"


ANSWER_MAX = 400


class AnswerOut(BaseModel):
    answer: str = Field(max_length=ANSWER_MAX)


ANSWER_PROMPT = (
    "Ты пишешь реплику заявителя учебного вызова 112. Перепиши ОДИН ответ заявителя на вопрос оператора по "
    "комментарию преподавателя: разговорная речь, 1–3 предложения, без новых фактов — адрес, имена, число "
    'пострадавших и признаки бери только из легенды. Верни JSON {"answer": текст ответа}.'
)


@dataclass(frozen=True, kw_only=True)
class EditAnswer(Command):
    """Перегенерация или правка ОДНОГО ответа заявителя из прогона (ТЗ 3.4: «по комментарию преподавателя система
    перегенерирует вопрос / ответ»). `text` — вписать вручную (работает без модели), `comment` — переписать моделью,
    ни того ни другого — вернуть ответ по легенде. Сценарий возвращается в черновики, как при любой правке."""

    actor: Principal
    scenario_id: UUID
    topic: str
    text: str | None = None
    comment: str | None = None
    meta: RequestMeta = field(default_factory=RequestMeta)


class EditAnswerHandler(EditScenarioHandler):
    async def _rewrite(self, s: Scenario, topic: str, question: str, current: str, comment: str) -> str:
        model = self._router.for_task(AITask.SCENARIO_GENERATION)
        if model.provider_name == "fake":
            raise DomainError(
                "Переписать ответ по комментарию может только подключённая модель (config/ai.yaml) — "
                "без неё впишите ответ вручную",
                code="ai_unavailable",
            )
        facts = {
            "легенда": {k: s.legend.get(k) for k in ("what", "details", "address", "applicant", "victims", "facts")},
            "тема_вопроса": topic,
            "вопрос_оператора": question,
            "текущий_ответ": current,
            "комментарий_преподавателя": comment,
        }
        try:
            result = await model.complete(
                [
                    ChatMessage(role="system", content=ANSWER_PROMPT),
                    ChatMessage(role="user", content=json.dumps(facts, ensure_ascii=False, default=str)),
                ],
                schema=AnswerOut,
            )
            out = result.parsed if isinstance(result.parsed, AnswerOut) else AnswerOut.model_validate_json(result.text)
        except (ExternalServiceError, ValueError) as e:
            raise DomainError(f"Модель недоступна: {e}", code="ai_unavailable") from e
        return out.answer

    async def __call__(self, cmd: EditAnswer) -> EditResult:  # type: ignore[override]
        if cmd.topic not in ANSWER_TOPICS:
            raise DomainError(f"Нет темы ответа «{cmd.topic}»", code="bad_answer_topic")
        s = await self._repo.get(cmd.scenario_id)
        if s is None:
            raise NotFoundError("Сценарий не найден", code="scenario_not_found")
        answers = dict(s.legend.get("answers") or {})
        if cmd.text is not None and cmd.text.strip():
            text = " ".join(cmd.text.split())
        elif cmd.comment and cmd.comment.strip():
            text = " ".join(
                (
                    await self._rewrite(
                        s, cmd.topic, QUESTION_OF.get(cmd.topic, cmd.topic), answers.get(cmd.topic, ""), cmd.comment
                    )
                ).split()
            )
        else:
            text = ""
        if len(text) > ANSWER_MAX:
            raise DomainError(f"Ответ — не длиннее {ANSWER_MAX} символов", code="answer_too_long")
        if text:
            problems = answer_fact_errors(s.legend, cmd.topic, text)
            if problems:
                raise DomainError(
                    "Ответ меняет факты легенды: " + "; ".join(problems) + " — эталон карточки строится по ним",
                    code="answer_changes_facts",
                )
            answers[cmd.topic] = text
        else:
            answers.pop(cmd.topic, None)
        s.legend["answers"] = answers
        if not answers:
            s.legend.pop("answers", None)
        remarks, by = await self._check_grammar(s, {f"ответ: {cmd.topic}": text}) if text else ([], "rules")
        s.legend["grammar_check"] = {
            "at": datetime.now(UTC).isoformat(),
            "by": by,
            "remarks": [asdict(r) for r in remarks],
        }
        s.status = ScenarioStatus.DRAFT
        s.approved_by = None
        try:
            await self._repo.save(s)
            await self._audit.record(
                AuditEntry(
                    event=AuditEvent.SCENARIO_EDITED,
                    actor=cmd.actor,
                    meta=cmd.meta,
                    description=f"{s.title}: ответ заявителя «{cmd.topic}» "
                    + (
                        "переписан моделью по комментарию"
                        if not cmd.text and cmd.comment
                        else "изменён"
                        if text
                        else "по легенде"
                    ),
                    object_type="scenario",
                    object_id=str(s.id),
                )
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return EditResult(status=s.status.value, grammar=remarks, checked_by=by)


QUESTION_OF = {
    "opening": "Служба 112, что у вас случилось?",
    "what": "Что у вас случилось?",
    "address": "Назовите адрес.",
    "floor": "Подъезд, этаж, квартира?",
    "victims": "Есть пострадавшие?",
    "name": "Как вас зовут?",
    "status": "Кем вы приходитесь пострадавшему?",
    "phone": "Ваш номер телефона?",
}


@dataclass(frozen=True, kw_only=True)
class SetScenarioPsy(Command):
    """Закрепить психологический профиль заявителя за сценарием (п. 3.7). Легенда и эталоны не меняются, поэтому
    сценарий остаётся утверждённым: профиль — модификатор, а не правка сценария (ADR-0012)."""

    actor: Principal
    scenario_id: UUID
    profile: str | None
    meta: RequestMeta = field(default_factory=RequestMeta)


class SetScenarioPsyHandler:
    def __init__(self, repo: ScenarioRepository, catalog: PsyCatalog, audit: AuditRecorder, uow: UnitOfWork) -> None:
        self._repo = repo
        self._catalog = catalog
        self._audit = audit
        self._uow = uow

    async def __call__(self, cmd: SetScenarioPsy) -> str | None:
        s = await self._repo.get(cmd.scenario_id)
        if s is None:
            raise NotFoundError("Сценарий не найден", code="scenario_not_found")
        profile = self._catalog.get(cmd.profile) if cmd.profile else None
        if cmd.profile and profile is None:
            raise DomainError("Нет такого психологического профиля", code="unknown_psy_profile")
        s.psy_profile = profile.id if profile else None
        try:
            await self._repo.save(s)
            await self._audit.record(
                AuditEntry(
                    event=AuditEvent.SCENARIO_EDITED,
                    actor=cmd.actor,
                    meta=cmd.meta,
                    description=f"{s.title}: профиль заявителя — {profile.title if profile else 'без профиля'}",
                    object_type="scenario",
                    object_id=str(s.id),
                    data={"psy_profile": s.psy_profile},
                )
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return s.psy_profile
