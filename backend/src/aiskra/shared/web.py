"""HTTP-адаптер общего ядра безопасности (ADR-0010): FastAPI-зависимости для api-слоя модулей и main.

- `CurrentPrincipal` — текущий пользователь; нет действующей сессии → 401.
- `require(Permission.X)` — проверка права; отказ → 403 и запись «Отказ в доступе» в аудит.

Как именно находится пользователь (cookie → сессия в БД), решает composition root:
заглушки `provide_principal` и `provide_isolated_audit` связываются в `aiskra.bootstrap.wire`.
Слой application этот модуль не импортирует (там запрещён FastAPI, см. import-linter).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request

from aiskra.shared.audit import AuditEntry, AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.di import provider_stub
from aiskra.shared.security import Permission, Principal

provide_principal = provider_stub("identity.CurrentPrincipal")
provide_isolated_audit = provider_stub("audit.IsolatedAuditRecorder")

CurrentPrincipal = Annotated[Principal, Depends(provide_principal)]


def request_meta(request: Request) -> RequestMeta:
    """IP и клиент. За nginx IP берётся из X-Forwarded-For (uvicorn --proxy-headers)."""
    return RequestMeta(
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


Meta = Annotated[RequestMeta, Depends(request_meta)]


def require(permission: Permission, *alternatives: Permission) -> Callable[..., Awaitable[Principal]]:
    """Зависимость «нужно право» (или любое из `alternatives`). Возвращает субъекта для команды."""

    async def dependency(
        principal: CurrentPrincipal,
        request: Request,
        audit: Annotated[AuditRecorder, Depends(provide_isolated_audit)],
    ) -> Principal:
        if not principal.can(permission) and not any(principal.can(p) for p in alternatives):
            await audit.record(
                AuditEntry(
                    event=AuditEvent.ACCESS_DENIED,
                    actor=principal,
                    description=f"{request.method} {request.url.path}: нет права «{permission.value}»",
                    meta=request_meta(request),
                )
            )
            principal.ensure(permission)
        return principal

    dependency.__name__ = f"require_{permission.name.lower()}"
    return dependency
