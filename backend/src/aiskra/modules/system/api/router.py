"""HTTP-адаптер модуля system. Тонкий: схема → команда/запрос → обработчик → схема."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends

from aiskra.modules.system.api import deps
from aiskra.modules.system.api.schemas import AIConfigOut, ProbeRequest, ProbeResponse, TaskInfoOut
from aiskra.modules.system.application.commands.probe_model import ProbeModel, ProbeModelHandler
from aiskra.modules.system.application.queries.get_ai_config import GetAIConfig, GetAIConfigHandler
from aiskra.shared.security import Permission
from aiskra.shared.web import require

router = APIRouter(prefix="/system", tags=["system"], dependencies=[Depends(require(Permission.SYSTEM_MANAGE))])


@router.get("/ai", response_model=AIConfigOut, summary="Назначение моделей на ИИ-задачи (запрос)")
async def get_ai_config(
    handler: Annotated[GetAIConfigHandler, Depends(deps.provide_get_ai_config_handler)],
) -> AIConfigOut:
    view = await handler(GetAIConfig())
    return AIConfigOut(
        allow_external=view.allow_external,
        default_provider=view.default_provider,
        tasks=[TaskInfoOut(**asdict(t)) for t in view.tasks],
    )


@router.post("/ai/probe", response_model=ProbeResponse, summary="Пробный запрос к модели задачи (команда)")
async def probe_model(
    body: ProbeRequest,
    handler: Annotated[ProbeModelHandler, Depends(deps.provide_probe_model_handler)],
) -> ProbeResponse:
    result = await handler(ProbeModel(prompt=body.prompt, task=body.task))
    return ProbeResponse(**asdict(result))
