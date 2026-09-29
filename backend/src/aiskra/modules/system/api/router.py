"""HTTP-адаптер модуля system. Тонкий: схема → команда/запрос → обработчик → схема."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Protocol

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from aiskra.modules.system.api import deps
from aiskra.modules.system.api.schemas import AIConfigOut, ProbeRequest, ProbeResponse, TaskInfoOut
from aiskra.modules.system.application.commands.backups import (
    CreateBackup,
    CreateBackupHandler,
    ListBackups,
    ListBackupsHandler,
    RestoreBackup,
    RestoreBackupHandler,
)
from aiskra.modules.system.application.commands.probe_model import ProbeModel, ProbeModelHandler
from aiskra.modules.system.application.commands.settings import (
    LIMITS,
    GetSettings,
    GetSettingsHandler,
    UpdateSettings,
    UpdateSettingsHandler,
)
from aiskra.modules.system.application.ports.admin import BackupInfo, LogRecord, ServiceState
from aiskra.modules.system.application.queries.admin import (
    Alert,
    GetAlerts,
    GetAlertsHandler,
    GetStatus,
    GetStatusHandler,
    RecentLogs,
    RecentLogsHandler,
)
from aiskra.modules.system.application.queries.get_ai_config import GetAIConfig, GetAIConfigHandler
from aiskra.shared.errors import NotFoundError
from aiskra.shared.security import Permission, Principal
from aiskra.shared.web import Meta, require


class FileBackupPort(Protocol):
    def path(self, name: str) -> Path: ...


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


# ------------------------------------------------------------------ п. 5.2: панель администратора
Admin = Annotated[Principal, Depends(require(Permission.SYSTEM_MANAGE))]


class SettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    values: dict[str, float] = Field(description="Параметры раздела; пределы — в GET /system/settings/limits")


class RestoreIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: str = Field(description="Слово «ВОССТАНОВИТЬ»")


@router.get("/settings", summary="Настройки системы (со значениями по умолчанию)")
async def get_settings(
    handler: Annotated[GetSettingsHandler, Depends(deps.provide_get_settings)],
) -> dict[str, dict[str, float]]:
    return await handler(GetSettings())


@router.get("/settings/limits", summary="Пределы параметров настроек: [по умолчанию, минимум, максимум]")
async def settings_limits() -> dict[str, dict[str, tuple[float, float, float]]]:
    return LIMITS


@router.put("/settings/{key}", summary="Изменить раздел настроек (аудит)")
async def update_settings(
    key: str,
    body: SettingsIn,
    actor: Admin,
    meta: Meta,
    handler: Annotated[UpdateSettingsHandler, Depends(deps.provide_update_settings)],
) -> dict[str, float]:
    return await handler(UpdateSettings(actor=actor, key=key, values=body.values, meta=meta))


@router.get("/status", response_model=list[ServiceState], summary="Состояние сервисов: БД, ИИ, телефония, копии")
async def status(handler: Annotated[GetStatusHandler, Depends(deps.provide_status)]) -> list[ServiceState]:
    return await handler(GetStatus())


@router.get("/alerts", response_model=list[Alert], summary="Оповещения о сбоях: сервисы не в норме, ошибки в логе")
async def alerts(handler: Annotated[GetAlertsHandler, Depends(deps.provide_alerts)]) -> list[Alert]:
    return await handler(GetAlerts())


@router.get("/logs", response_model=list[LogRecord], summary="Последние записи лога процесса")
async def logs(
    handler: Annotated[RecentLogsHandler, Depends(deps.provide_logs)],
    level: str = "INFO",
    limit: int = 200,
    q: str = "",
) -> list[LogRecord]:
    return await handler(RecentLogs(level=level, limit=limit, q=q))


@router.get("/backups", response_model=list[BackupInfo], summary="Резервные копии")
async def list_backups(handler: Annotated[ListBackupsHandler, Depends(deps.provide_list_backups)]) -> list[BackupInfo]:
    return await handler(ListBackups())


@router.post("/backups", response_model=BackupInfo, status_code=201, summary="Создать резервную копию")
async def create_backup(
    actor: Admin, meta: Meta, handler: Annotated[CreateBackupHandler, Depends(deps.provide_create_backup)]
) -> BackupInfo:
    return await handler(CreateBackup(actor=actor, meta=meta))


@router.get("/backups/{name}", summary="Скачать резервную копию")
async def download_backup(
    name: str, store: Annotated[FileBackupPort, Depends(deps.provide_backup_file)]
) -> FileResponse:
    try:
        path = store.path(name)
    except FileNotFoundError as e:
        raise NotFoundError("Копия не найдена", code="backup_not_found") from e
    return FileResponse(path, media_type="application/gzip", filename=name)


@router.post("/backups/{name}/restore", response_model=BackupInfo, summary="Восстановить из копии (все выйдут)")
async def restore_backup(
    name: str,
    body: RestoreIn,
    actor: Admin,
    meta: Meta,
    handler: Annotated[RestoreBackupHandler, Depends(deps.provide_restore_backup)],
) -> BackupInfo:
    return await handler(RestoreBackup(actor=actor, name=name, confirm=body.confirm, meta=meta))
