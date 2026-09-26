"""Команды сценариев (п. 3.2): генерация банка, утверждение, архив.

Генерация: строка классификатора (по выбранным группам) → случайный дом из адресного справочника → службы по
правилам классификатора (1.5) → модель пишет «своими словами» описание и первую реплику (`scenario_generation`,
структурированный ответ). Без модели — шаблоны `offline_story`. Эталон собирается правилами, не моделью."""

from __future__ import annotations

import json
import logging
import random
from collections.abc import Mapping
from dataclasses import dataclass, field
from uuid import UUID

from pydantic import BaseModel, Field

from aiskra.ai.ports import ChatMessage
from aiskra.ai.prompts import load_prompt
from aiskra.ai.router import ModelRouter
from aiskra.ai.tasks import AITask
from aiskra.modules.training.application.ports.scenarios import ScenarioFactsSource, ScenarioRepository
from aiskra.modules.training.domain.scenario import FLAG_FACTS, Scenario, ScenarioStatus, build_scenario, offline_story
from aiskra.shared.application import Command, UnitOfWork
from aiskra.shared.audit import AuditEntry, AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.errors import DomainError, ExternalServiceError, NotFoundError
from aiskra.shared.security import Principal

log = logging.getLogger(__name__)
MAX_BATCH = 50


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
    meta: RequestMeta = field(default_factory=RequestMeta)


class ScenarioGenerator:
    """Одна генерация без сохранения — используется и командой, и входящим вызовом при пустом банке."""

    def __init__(self, facts: ScenarioFactsSource, router: ModelRouter) -> None:
        self._facts = facts
        self._router = router

    async def _story(
        self, incident_facts: Mapping[str, object], fallback: dict[str, str]
    ) -> tuple[dict[str, str], str]:
        model = self._router.for_task(AITask.SCENARIO_GENERATION)
        if model.provider_name == "fake":
            return fallback, "offline"
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

    async def generate(self, rng: random.Random, groups: list[int], difficulty: int, author: UUID | None) -> Scenario:
        incident = await self._facts.pick_incident(rng, groups or None)
        address = await self._facts.pick_address(rng)
        flags = [f for f in incident.flags if f in FLAG_FACTS and rng.random() < 0.5]
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
        story, source = await self._story(facts, fallback)
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
                scenario = await self._gen.generate(rng, cmd.groups, cmd.difficulty, author)
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
                    data={"groups": cmd.groups, "count": len(ids)},
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
        if cmd.approve:
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

    async def __call__(self, cmd: EditScenario) -> str:
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
        return s.status.value
