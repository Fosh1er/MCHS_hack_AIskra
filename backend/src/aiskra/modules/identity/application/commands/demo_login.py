"""Команда: демо-вход одной кнопкой без пароля (F2, только режимы demo и dev).

Входят только учётки из списка демо-стенда (`DEMO_USERS`), администратор — никогда: его нет в списке,
а роль ещё раз проверяется по базе. Сессия — обычная, как после входа по паролю, с номером АРМ
учётки по умолчанию; в аудит пишется `auth.demo_login`.

Временная блокировка после неверных паролей демо-вход не закрывает: на публичном стенде её мог бы
включить кто угодно, и демо-учётка перестала бы работать. Блокировка администратором — закрывает.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aiskra.modules.identity.application.commands.login import LoginHandler, LoginResult
from aiskra.modules.identity.application.ports.auth import UserRepository
from aiskra.modules.identity.application.ports.demo import DemoPolicy
from aiskra.shared.application import Clock, Command, UnitOfWork
from aiskra.shared.audit import AuditEntry, AuditEvent, AuditRecorder, RequestMeta
from aiskra.shared.errors import AuthenticationError, NotFoundError

NOT_DEMO = "Демо-учётка не найдена"


@dataclass(frozen=True, kw_only=True)
class DemoLogin(Command):
    login: str
    meta: RequestMeta = field(default_factory=RequestMeta)


class DemoLoginHandler:
    def __init__(
        self,
        sessions: LoginHandler,
        users: UserRepository,
        audit: AuditRecorder,
        uow: UnitOfWork,
        clock: Clock,
        demo: DemoPolicy,
    ) -> None:
        self._sessions = sessions
        self._users = users
        self._audit = audit
        self._uow = uow
        self._clock = clock
        self._demo = demo

    async def __call__(self, cmd: DemoLogin) -> LoginResult:
        login = cmd.login.strip().lower()
        spec = self._demo.find(login)
        user = await self._users.get_by_login(login) if spec else None
        if spec is None or user is None or user.is_admin:
            raise NotFoundError(NOT_DEMO, code="demo_account_not_found")
        if not user.is_active:
            await self._audit.record(
                AuditEntry(
                    event=AuditEvent.LOGIN_FAILED,
                    actor_login=login,
                    description="Демо-вход: учётная запись заблокирована",
                    object_type="user",
                    object_id=str(user.id),
                    meta=cmd.meta,
                )
            )
            await self._uow.commit()
            raise AuthenticationError(
                "Учётная запись заблокирована. Обратитесь к администратору", code="account_blocked"
            )
        return await self._sessions.open_session(
            user, arm_number=spec.arm_number, meta=cmd.meta, now=self._clock.now(), event=AuditEvent.DEMO_LOGIN
        )
