"""Swagger (`/docs`) и схема API (`/openapi.json`) в prod — только вошедшему администратору (F6.3, ADR-0015).

В demo и dev их отдаёт сам FastAPI без входа, как раньше. В prod встроенные маршруты выключены, а эти два
проверяют сессию и право `system.manage`: без входа — 401, у другой роли — 403 (и запись в аудит, как везде).
Схема в ответе не попадает в саму себя (`include_in_schema=False`).
"""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse

from aiskra.shared.security import Permission
from aiskra.shared.web import require

DOCS_URL = "/docs"
OPENAPI_URL = "/openapi.json"


def mount_admin_docs(app: FastAPI) -> None:
    admin_only = [Depends(require(Permission.SYSTEM_MANAGE))]

    @app.get(OPENAPI_URL, include_in_schema=False, dependencies=admin_only)
    async def openapi_json() -> JSONResponse:
        return JSONResponse(app.openapi())

    @app.get(DOCS_URL, include_in_schema=False, dependencies=admin_only)
    async def swagger_ui() -> HTMLResponse:
        return get_swagger_ui_html(openapi_url=OPENAPI_URL, title=f"{app.title} — API")
