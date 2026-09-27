"""Порт `ValidationSource` модуля assessment (п. 3.5) поверх банка сценариев (training) и автоподбора служб
(dictionaries): эталон сценария сверяется с тем, что подберёт классификатор сейчас."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aiskra.modules.assessment.domain.validation import ScenarioCase
from aiskra.modules.dictionaries.application.queries.resolve_services import ResolveServices, ResolveServicesHandler
from aiskra.modules.dictionaries.infrastructure.reader import SqlDictionaryReader
from aiskra.modules.training.infrastructure.models import ScenarioModel


class ScenarioBankCases:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def cases(self, limit: int) -> list[ScenarioCase]:
        rows = (
            (
                await self._s.execute(
                    select(ScenarioModel)
                    .where(ScenarioModel.status == "approved")
                    .order_by(ScenarioModel.created_at)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        resolve = ResolveServicesHandler(SqlDictionaryReader(self._s))
        out = []
        for r in rows:
            ref = dict(r.reference_card or {})
            routed: set[str] | None = None
            if ref.get("incident_types"):
                address = ref.get("address") or {}
                resolved = await resolve(
                    ResolveServices(
                        incident_types=list(ref["incident_types"]),
                        flags=list(ref.get("card_flags") or []),
                        okrug=address.get("okrug") or None,
                        district=address.get("district") or None,
                    )
                )
                routed = {s.code for s in resolved.services}
            out.append(ScenarioCase(dict(r.legend or {}), ref, dict(r.reference_dds or {}), routed))
        return out
