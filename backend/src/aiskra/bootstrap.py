"""Composition root (ADR-0004): единственное место, где порты связываются с адаптерами.

- build_services — собрать сервисы процесса по настройкам и config/ai.yaml;
- wire — подменить заглушки провайдеров в API модулей реальными фабриками.

Добавляя обработчик в модуле: объявите заглушку в `modules/<m>/api/deps.py` и свяжите её здесь.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncSession

from aiskra.ai.adapters.factory import build_router, build_stt, build_tts
from aiskra.ai.config import load_ai_config
from aiskra.modules.audit.api import deps as audit_deps
from aiskra.modules.audit.application.queries.search_audit import ListEventTypesHandler, SearchAuditHandler
from aiskra.modules.audit.infrastructure.reader import SqlAuditReader
from aiskra.modules.audit.infrastructure.recorder import IsolatedAuditRecorder, SqlAuditRecorder
from aiskra.modules.dictionaries.api import deps as dict_deps
from aiskra.modules.dictionaries.application.commands.import_dictionaries import ImportDictionariesHandler
from aiskra.modules.dictionaries.application.queries.incident_types import (
    GetIncidentTypeHandler,
    GetQuestionnaireTreeHandler,
    SearchCardTypesHandler,
    SearchIncidentTypesHandler,
)
from aiskra.modules.dictionaries.application.queries.reference import (
    ListEnumHandler,
    ListServicesHandler,
    ListTerritoryHandler,
)
from aiskra.modules.dictionaries.infrastructure.reader import SqlDictionaryReader
from aiskra.modules.dictionaries.infrastructure.sources import XlsxClassifierSource, YamlCuratedSource
from aiskra.modules.dictionaries.infrastructure.writer import SqlDictionaryWriter
from aiskra.modules.identity.api import deps as identity_deps
from aiskra.modules.identity.api.cookies import SessionCookie
from aiskra.modules.identity.application.commands.create_user import CreateUserHandler
from aiskra.modules.identity.application.commands.login import LoginHandler
from aiskra.modules.identity.application.commands.logout import LogoutHandler
from aiskra.modules.identity.application.commands.reset_password import ResetPasswordHandler
from aiskra.modules.identity.application.commands.set_user_blocked import SetUserBlockedHandler
from aiskra.modules.identity.application.commands.update_user import UpdateUserHandler
from aiskra.modules.identity.application.ports.auth import AuthPolicy
from aiskra.modules.identity.application.queries.list_users import ListUsersHandler
from aiskra.modules.identity.application.queries.resolve_session import ResolveSession, ResolveSessionHandler
from aiskra.modules.identity.domain.user import LockoutPolicy
from aiskra.modules.identity.infrastructure.reader import SqlSessionReader, SqlUserReader
from aiskra.modules.identity.infrastructure.repositories import SqlSessionRepository, SqlUserRepository
from aiskra.modules.identity.infrastructure.security import ScryptPasswordHasher, SessionTokenIssuer
from aiskra.modules.system.api import deps as system_deps
from aiskra.modules.system.application.commands.probe_model import ProbeModelHandler
from aiskra.modules.system.application.queries.get_ai_config import GetAIConfigHandler
from aiskra.platform.db import SqlAlchemyUnitOfWork, create_engine, create_session_factory
from aiskra.platform.deps import get_session
from aiskra.platform.services import Services
from aiskra.platform.settings import Settings
from aiskra.shared import web
from aiskra.shared.application import SystemClock
from aiskra.shared.cache import CachePort, InMemoryTTLCache, NullCache
from aiskra.shared.security import Principal


def build_services(settings: Settings) -> Services:
    ai_config = load_ai_config(settings.ai_config_path)
    cache: CachePort = (
        InMemoryTTLCache(max_items=ai_config.cache.max_items) if ai_config.cache.backend == "memory" else NullCache()
    )
    engine = create_engine(settings.database_url)
    return Services(
        settings=settings,
        ai_config=ai_config,
        engine=engine,
        session_factory=create_session_factory(engine),
        cache=cache,
        model_router=build_router(ai_config, cache),
        tts=build_tts(ai_config, cache),
        stt=build_stt(ai_config),
    )


Session = Annotated[AsyncSession, Depends(get_session)]


def _dict_query(handler_cls: Callable[[SqlDictionaryReader], Any]) -> Callable[..., Any]:
    """Фабрика обработчика запроса справочников: сессия запроса → SQL-reader → обработчик."""

    def factory(session: Session) -> Any:
        return handler_cls(SqlDictionaryReader(session))

    return factory


def build_import_handler(settings: Settings, session: AsyncSession) -> ImportDictionariesHandler:
    return ImportDictionariesHandler(
        classifier=XlsxClassifierSource(settings.classifier_path),
        curated=YamlCuratedSource(settings.dictionaries_dir),
        writer=SqlDictionaryWriter(session),
        audit=SqlAuditRecorder(session),
        uow=SqlAlchemyUnitOfWork(session),
    )


@dataclass(frozen=True)
class IdentityAdapters:
    """Адаптеры входа, общие для процесса (ADR-0010). Хешер создаётся один раз: он готовит «пустой» хеш."""

    hasher: ScryptPasswordHasher
    tokens: SessionTokenIssuer
    clock: SystemClock
    policy: AuthPolicy
    cookie: SessionCookie


def build_identity_adapters(settings: Settings) -> IdentityAdapters:
    return IdentityAdapters(
        hasher=ScryptPasswordHasher(n=settings.password_scrypt_n),
        tokens=SessionTokenIssuer(),
        clock=SystemClock(),
        policy=AuthPolicy(
            session_ttl=timedelta(hours=settings.session_ttl_hours),
            lockout=LockoutPolicy(
                max_attempts=settings.login_max_attempts, lock_for=timedelta(minutes=settings.login_lock_minutes)
            ),
        ),
        cookie=SessionCookie(name=settings.session_cookie_name, secure=settings.session_cookie_secure),
    )


def build_create_user_handler(ida: IdentityAdapters, session: AsyncSession) -> CreateUserHandler:
    return CreateUserHandler(
        SqlUserRepository(session), ida.hasher, SqlAuditRecorder(session), SqlAlchemyUnitOfWork(session)
    )


def _wire_identity_and_audit(app: FastAPI, services: Services) -> None:
    ov = app.dependency_overrides
    ida = build_identity_adapters(services.settings)

    async def current_principal(request: Request, session: Session) -> Principal:
        handler = ResolveSessionHandler(SqlSessionReader(session), ida.tokens, ida.clock)
        return await handler(ResolveSession(token=request.cookies.get(ida.cookie.name)))

    def login(session: Session) -> LoginHandler:
        return LoginHandler(
            SqlUserRepository(session),
            SqlSessionRepository(session),
            ida.hasher,
            ida.tokens,
            SqlAuditRecorder(session),
            SqlAlchemyUnitOfWork(session),
            ida.clock,
            ida.policy,
        )

    def logout(session: Session) -> LogoutHandler:
        return LogoutHandler(
            SqlSessionRepository(session), SqlAuditRecorder(session), SqlAlchemyUnitOfWork(session), ida.clock
        )

    def create_user(session: Session) -> CreateUserHandler:
        return build_create_user_handler(ida, session)

    def update_user(session: Session) -> UpdateUserHandler:
        return UpdateUserHandler(SqlUserRepository(session), SqlAuditRecorder(session), SqlAlchemyUnitOfWork(session))

    def set_blocked(session: Session) -> SetUserBlockedHandler:
        return SetUserBlockedHandler(
            SqlUserRepository(session),
            SqlSessionRepository(session),
            SqlAuditRecorder(session),
            SqlAlchemyUnitOfWork(session),
            ida.clock,
        )

    def reset_password(session: Session) -> ResetPasswordHandler:
        return ResetPasswordHandler(
            SqlUserRepository(session),
            SqlSessionRepository(session),
            ida.hasher,
            SqlAuditRecorder(session),
            SqlAlchemyUnitOfWork(session),
            ida.clock,
        )

    def list_users(session: Session) -> ListUsersHandler:
        return ListUsersHandler(SqlUserReader(session))

    def search_audit(session: Session) -> SearchAuditHandler:
        return SearchAuditHandler(SqlAuditReader(session))

    ov[web.provide_principal] = current_principal
    ov[web.provide_isolated_audit] = lambda: IsolatedAuditRecorder(services.session_factory)
    ov[identity_deps.provide_session_cookie] = lambda: ida.cookie
    ov[identity_deps.provide_login] = login
    ov[identity_deps.provide_logout] = logout
    ov[identity_deps.provide_create_user] = create_user
    ov[identity_deps.provide_update_user] = update_user
    ov[identity_deps.provide_set_user_blocked] = set_blocked
    ov[identity_deps.provide_reset_password] = reset_password
    ov[identity_deps.provide_list_users] = list_users
    ov[audit_deps.provide_search_audit] = search_audit
    ov[audit_deps.provide_event_types] = ListEventTypesHandler


def wire(app: FastAPI, services: Services) -> None:
    ov = app.dependency_overrides
    # --- system
    ov[system_deps.provide_probe_model_handler] = lambda: ProbeModelHandler(services.model_router)
    ov[system_deps.provide_get_ai_config_handler] = lambda: GetAIConfigHandler(
        services.model_router,
        allow_external=services.ai_config.allow_external,
        default_provider=services.ai_config.default_provider,
    )

    # --- dictionaries (п. 0.2)
    def import_factory(session: Session) -> ImportDictionariesHandler:
        return build_import_handler(services.settings, session)

    ov[dict_deps.provide_import] = import_factory
    ov[dict_deps.provide_search_card_types] = _dict_query(SearchCardTypesHandler)
    ov[dict_deps.provide_questionnaire] = _dict_query(GetQuestionnaireTreeHandler)
    ov[dict_deps.provide_search_incident_types] = _dict_query(SearchIncidentTypesHandler)
    ov[dict_deps.provide_get_incident_type] = _dict_query(GetIncidentTypeHandler)
    ov[dict_deps.provide_list_services] = _dict_query(ListServicesHandler)
    ov[dict_deps.provide_list_territory] = _dict_query(ListTerritoryHandler)
    ov[dict_deps.provide_list_enum] = _dict_query(ListEnumHandler)

    # --- identity и audit (п. 0.3)
    _wire_identity_and_audit(app, services)
    # --- сюда добавляются связывания модулей incidents, training … (п. 1.x)
