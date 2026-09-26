"""HTTP API identity: вход и выход (`/auth`), управление учётными записями (`/users`, только администратор)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from aiskra.modules.identity.api import deps
from aiskra.modules.identity.api.cookies import SessionCookie
from aiskra.modules.identity.api.schemas import (
    BlockIn,
    LoginIn,
    LoginOut,
    MeOut,
    PasswordResetIn,
    UserCreatedOut,
    UserCreateIn,
    UserOut,
    UserPageOut,
    UserUpdatedOut,
    UserUpdateIn,
)
from aiskra.modules.identity.application.commands.create_user import CreateUser, CreateUserHandler
from aiskra.modules.identity.application.commands.login import Login, LoginHandler
from aiskra.modules.identity.application.commands.logout import Logout, LogoutHandler
from aiskra.modules.identity.application.commands.reset_password import ResetPassword, ResetPasswordHandler
from aiskra.modules.identity.application.commands.set_user_blocked import SetUserBlocked, SetUserBlockedHandler
from aiskra.modules.identity.application.commands.update_user import UpdateUser, UpdateUserHandler
from aiskra.modules.identity.application.queries.list_users import ListUsers, ListUsersHandler
from aiskra.shared.security import Permission, Principal, Role
from aiskra.shared.web import CurrentPrincipal, Meta, require

Cookie = Annotated[SessionCookie, Depends(deps.provide_session_cookie)]
Admin = Annotated[Principal, Depends(require(Permission.USERS_MANAGE))]

auth_router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(prefix="/users", tags=["users"])


@auth_router.post("/login", response_model=LoginOut, summary="Вход: логин, пароль, номер АРМ (публичный)")
async def login(
    body: LoginIn,
    meta: Meta,
    response: Response,
    cookie: Cookie,
    handler: Annotated[LoginHandler, Depends(deps.provide_login)],
) -> LoginOut:
    result = await handler(Login(login=body.login, password=body.password, arm_number=body.arm_number, meta=meta))
    cookie.set(response, result.token, result.expires_at)
    return LoginOut(**MeOut.of(result.principal).model_dump(), expires_at=result.expires_at)


@auth_router.post("/logout", status_code=204, summary="Выход: отзыв текущей сессии")
async def logout(
    principal: CurrentPrincipal,
    meta: Meta,
    response: Response,
    cookie: Cookie,
    handler: Annotated[LogoutHandler, Depends(deps.provide_logout)],
) -> None:
    await handler(Logout(actor=principal, meta=meta))
    cookie.clear(response)


@auth_router.get("/me", response_model=MeOut, summary="Текущий пользователь, роль и права")
async def me(principal: CurrentPrincipal) -> MeOut:
    return MeOut.of(principal)


@users_router.get("", response_model=UserPageOut, summary="Пользователи (поиск, фильтры роли и статуса)")
async def list_users(
    _: Admin,
    handler: Annotated[ListUsersHandler, Depends(deps.provide_list_users)],
    q: str = "",
    role: Role | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> UserPageOut:
    page = await handler(ListUsers(q=q, role=role.value if role else None, status=status, limit=limit, offset=offset))
    return UserPageOut(items=[UserOut(**asdict(u)) for u in page.items], total=page.total)


@users_router.post("", response_model=UserCreatedOut, status_code=201, summary="Создать пользователя")
async def create_user(
    body: UserCreateIn,
    actor: Admin,
    meta: Meta,
    handler: Annotated[CreateUserHandler, Depends(deps.provide_create_user)],
) -> UserCreatedOut:
    created = await handler(
        CreateUser(
            actor=actor,
            login=body.login,
            full_name=body.full_name,
            role=body.role,
            password=body.password,
            operator_number=body.operator_number,
            meta=meta,
        )
    )
    return UserCreatedOut(id=created.id, login=created.login)


@users_router.patch("/{user_id}", response_model=UserUpdatedOut, summary="Изменить ФИО, роль, номер оператора")
async def update_user(
    user_id: UUID,
    body: UserUpdateIn,
    actor: Admin,
    meta: Meta,
    handler: Annotated[UpdateUserHandler, Depends(deps.provide_update_user)],
) -> UserUpdatedOut:
    changed = await handler(
        UpdateUser(
            actor=actor,
            user_id=user_id,
            full_name=body.full_name,
            role=body.role,
            operator_number=body.operator_number,
            meta=meta,
        )
    )
    return UserUpdatedOut(changed=changed)


@users_router.post("/{user_id}/block", status_code=204, summary="Заблокировать (сессии отзываются сразу)")
async def block_user(
    user_id: UUID,
    body: BlockIn,
    actor: Admin,
    meta: Meta,
    handler: Annotated[SetUserBlockedHandler, Depends(deps.provide_set_user_blocked)],
) -> None:
    await handler(SetUserBlocked(actor=actor, user_id=user_id, blocked=True, reason=body.reason, meta=meta))


@users_router.post("/{user_id}/unblock", status_code=204, summary="Разблокировать")
async def unblock_user(
    user_id: UUID,
    actor: Admin,
    meta: Meta,
    handler: Annotated[SetUserBlockedHandler, Depends(deps.provide_set_user_blocked)],
) -> None:
    await handler(SetUserBlocked(actor=actor, user_id=user_id, blocked=False, meta=meta))


@users_router.post("/{user_id}/password", status_code=204, summary="Задать новый пароль (сессии отзываются)")
async def reset_password(
    user_id: UUID,
    body: PasswordResetIn,
    actor: Admin,
    meta: Meta,
    handler: Annotated[ResetPasswordHandler, Depends(deps.provide_reset_password)],
) -> None:
    await handler(ResetPassword(actor=actor, user_id=user_id, new_password=body.new_password, meta=meta))
