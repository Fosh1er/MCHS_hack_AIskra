"""Запросы учебных материалов (п. 4.4): список с поиском, текст с найденными местами, выдержки для генерации."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from aiskra.modules.training.application.ports.materials import MaterialRepository, MaterialRow
from aiskra.modules.training.domain.material import CONTENT_TYPES, Material, best_passages
from aiskra.shared.application import Query
from aiskra.shared.errors import NotFoundError
from aiskra.shared.security import Permission, Principal


def _can_manage(actor: Principal) -> bool:
    return actor.can(Permission.SCENARIOS_MANAGE) or actor.can(Permission.SYSTEM_MANAGE)


@dataclass(frozen=True, kw_only=True)
class ListMaterials(Query):
    actor: Principal
    q: str = ""


class ListMaterialsHandler:
    def __init__(self, repo: MaterialRepository) -> None:
        self._repo = repo

    async def __call__(self, q: ListMaterials) -> list[MaterialRow]:
        return await self._repo.rows(q=q.q.strip(), visible_only=not _can_manage(q.actor))


@dataclass(frozen=True, kw_only=True)
class GetMaterial(Query):
    actor: Principal
    material_id: UUID
    q: str = ""


@dataclass(frozen=True)
class MaterialView:
    id: UUID
    title: str
    kind: str
    filename: str
    file_type: str
    content_type: str
    visible: bool
    use_in_prompts: bool
    text: str
    found: list[str]  # выдержки, где встречается запрос


async def load_visible(repo: MaterialRepository, actor: Principal, material_id: UUID) -> Material:
    m = await repo.get(material_id)
    if m is None or (not m.visible and not _can_manage(actor)):
        raise NotFoundError("Материал не найден", code="material_not_found")
    return m


class GetMaterialHandler:
    def __init__(self, repo: MaterialRepository) -> None:
        self._repo = repo

    async def __call__(self, q: GetMaterial) -> MaterialView:
        m = await load_visible(self._repo, q.actor, q.material_id)
        found = [p for _, p in best_passages(q.q, [(m.title, m.text)], limit=5)] if q.q.strip() else []
        return MaterialView(
            id=m.id,
            title=m.title,
            kind=m.kind.value,
            filename=m.filename,
            file_type=m.file_type.value,
            content_type=CONTENT_TYPES[m.file_type],
            visible=m.visible,
            use_in_prompts=m.use_in_prompts,
            text=m.text,
            found=found,
        )
