"""Заголовки безопасности ответов API (п. 6.2). Те же заголовки для SPA ставит nginx (infra/nginx/default.conf).

- nosniff, Referrer-Policy, Permissions-Policy (микрофон — только свой сайт, для голосового ввода);
- X-Frame-Options SAMEORIGIN: свой сайт может встраивать (просмотр PDF-материала), чужие — нет;
- Cache-Control: no-store для /api — ответы содержат персональные данные и результаты;
- HSTS — только когда запрос пришёл по HTTPS (за nginx: X-Forwarded-Proto, uvicorn --proxy-headers).
"""

from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

BASE = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"SAMEORIGIN"),
    (b"referrer-policy", b"same-origin"),
    (b"permissions-policy", b"camera=(), geolocation=(), microphone=(self)"),
    (b"cross-origin-opener-policy", b"same-origin"),
]
HSTS = (b"strict-transport-security", b"max-age=31536000")


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_api = scope.get("path", "").startswith("/api/")
        https = scope.get("scheme") == "https"

        async def wrapped(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {k.lower() for k, _ in headers}
                extra = [h for h in BASE if h[0] not in present]
                if is_api and b"cache-control" not in present:
                    extra.append((b"cache-control", b"no-store"))
                if https:
                    extra.append(HSTS)
                message["headers"] = headers + extra
            await send(message)

        await self.app(scope, receive, wrapped)
