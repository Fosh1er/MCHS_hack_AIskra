"""Cookie сессии (ADR-0010): HttpOnly, SameSite=Strict, Secure — в контуре с TLS."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fastapi import Response


@dataclass(frozen=True, kw_only=True)
class SessionCookie:
    name: str = "aiskra_session"
    secure: bool = False

    def set(self, response: Response, token: str, expires_at: datetime) -> None:
        response.set_cookie(
            self.name,
            token,
            expires=expires_at,
            httponly=True,
            secure=self.secure,
            samesite="strict",
            path="/",
        )

    def clear(self, response: Response) -> None:
        response.delete_cookie(self.name, httponly=True, secure=self.secure, samesite="strict", path="/")
