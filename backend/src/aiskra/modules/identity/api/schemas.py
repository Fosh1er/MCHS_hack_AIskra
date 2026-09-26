"""Pydantic-схемы HTTP API identity (отдельно от команд и DTO application-слоя)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from aiskra.shared.security import Principal, Role


class LoginIn(BaseModel):
    login: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)
    arm_number: str | None = Field(default=None, max_length=16, description="Номер АРМ, как на экране входа АРМ-112")


class MeOut(BaseModel):
    user_id: UUID
    login: str
    full_name: str
    role: Role
    role_title: str
    operator_number: str | None
    arm_number: str | None
    permissions: list[str]

    @classmethod
    def of(cls, p: Principal) -> MeOut:
        return cls(
            user_id=p.user_id,
            login=p.login,
            full_name=p.full_name,
            role=p.role,
            role_title=p.role.label,
            operator_number=p.operator_number,
            arm_number=p.arm_number,
            permissions=sorted(perm.value for perm in p.permissions),
        )


class LoginOut(MeOut):
    expires_at: datetime


class UserOut(BaseModel):
    id: UUID
    login: str
    full_name: str
    role: str
    status: str
    operator_number: str | None
    locked_until: datetime | None
    last_login_at: datetime | None
    created_at: datetime


class UserPageOut(BaseModel):
    items: list[UserOut]
    total: int


class UserCreateIn(BaseModel):
    login: str = Field(max_length=64)
    full_name: str = Field(max_length=255)
    role: Role
    password: str = Field(max_length=128)
    operator_number: str | None = Field(default=None, max_length=16)


class UserCreatedOut(BaseModel):
    id: UUID
    login: str


class UserUpdateIn(BaseModel):
    full_name: str | None = Field(default=None, max_length=255)
    role: Role | None = None
    operator_number: str | None = Field(default=None, max_length=16, description="Пустая строка — очистить")


class UserUpdatedOut(BaseModel):
    changed: list[str]


class BlockIn(BaseModel):
    reason: str = Field(default="", max_length=500)


class PasswordResetIn(BaseModel):
    new_password: str = Field(max_length=128)
