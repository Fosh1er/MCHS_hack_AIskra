"""Composition root (ADR-0004): единственное место, где порты связываются с адаптерами.

- build_services — собрать сервисы процесса по настройкам и config/ai.yaml;
- wire — подменить заглушки провайдеров в API модулей реальными фабриками.

Добавляя обработчик в модуле: объявите заглушку в `modules/<m>/api/deps.py` и свяжите её здесь.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncSession

from aiskra.ai.adapters.factory import build_router, build_stt, build_tts
from aiskra.ai.config import load_ai_config
from aiskra.ai.router import ModelRouter
from aiskra.integration.assessment_sources import IncidentAttempts
from aiskra.integration.session_sources import IncidentSystemCards, SessionFactsReader, SessionProgress, SqlScenarioBank
from aiskra.integration.system_sources import SystemRetentionPolicy, SystemServiceSwitches, SystemSessionDefaults
from aiskra.integration.training_sources import DictionaryScenarioFacts, IncidentCardContext
from aiskra.integration.validation_sources import ScenarioBankCases
from aiskra.modules.assessment.api import deps as assessment_deps
from aiskra.modules.assessment.application.commands.assess import AssessCardHandler
from aiskra.modules.assessment.application.commands.evaluate_session import EvaluateSessionHandler
from aiskra.modules.assessment.application.commands.feedback import SaveFeedbackHandler
from aiskra.modules.assessment.application.commands.override import OverrideAssessmentHandler
from aiskra.modules.assessment.application.judge import Judge
from aiskra.modules.assessment.application.psy_judge import PsyJudge
from aiskra.modules.assessment.application.queries.analytics import (
    NormReportHandler,
    ReadinessHandler,
    SessionDebriefHandler,
    StudentProfileHandler,
    SuggestAssignmentHandler,
)
from aiskra.modules.assessment.application.queries.assessments import GetAssessmentHandler, GroupInsightsHandler
from aiskra.modules.assessment.application.queries.feedback import DraftFeedbackHandler, MyFeedbackHandler
from aiskra.modules.assessment.application.queries.reports import (
    GetMySessionReportHandler,
    GetSessionReportHandler,
    MyProgressHandler,
)
from aiskra.modules.assessment.application.queries.validation import ValidationHandler
from aiskra.modules.assessment.infrastructure.repositories import SqlAssessmentRepository, SqlFeedbackStore
from aiskra.modules.audit.api import deps as audit_deps
from aiskra.modules.audit.application.commands.purge import PurgeAuditHandler
from aiskra.modules.audit.application.queries.search_audit import ListEventTypesHandler, SearchAuditHandler
from aiskra.modules.audit.infrastructure.purger import SqlAuditPurger
from aiskra.modules.audit.infrastructure.reader import SqlAuditReader
from aiskra.modules.audit.infrastructure.recorder import IsolatedAuditRecorder, SqlAuditRecorder
from aiskra.modules.dictionaries.api import deps as dict_deps
from aiskra.modules.dictionaries.application.commands.import_addresses import ImportAddressesHandler
from aiskra.modules.dictionaries.application.commands.import_dictionaries import ImportDictionariesHandler
from aiskra.modules.dictionaries.application.queries.addresses import (
    DistrictShapesHandler,
    HousesInBoxHandler,
    ReverseGeocodeHandler,
    SuggestAddressesHandler,
)
from aiskra.modules.dictionaries.application.queries.incident_types import (
    GetIncidentTypeHandler,
    GetQuestionnaireTreeHandler,
    SearchCardTypesHandler,
    SearchIncidentTypesHandler,
)
from aiskra.modules.dictionaries.application.queries.reference import (
    ListEnumHandler,
    ListGroupsHandler,
    ListServicesHandler,
    ListTerritoryHandler,
)
from aiskra.modules.dictionaries.application.queries.resolve_services import ResolveServicesHandler
from aiskra.modules.dictionaries.infrastructure.addresses import FileAddressSource, SqlAddressReader, SqlAddressWriter
from aiskra.modules.dictionaries.infrastructure.reader import SqlDictionaryReader
from aiskra.modules.dictionaries.infrastructure.sources import XlsxClassifierSource, YamlCuratedSource
from aiskra.modules.dictionaries.infrastructure.subordination import load_subordination
from aiskra.modules.dictionaries.infrastructure.writer import SqlDictionaryWriter
from aiskra.modules.identity.api import deps as identity_deps
from aiskra.modules.identity.api.cookies import SessionCookie
from aiskra.modules.identity.application.commands.create_user import CreateUserHandler
from aiskra.modules.identity.application.commands.groups import DeleteGroupHandler, SaveGroupHandler
from aiskra.modules.identity.application.commands.groups import ListGroupsHandler as IdentityListGroupsHandler
from aiskra.modules.identity.application.commands.login import LoginHandler
from aiskra.modules.identity.application.commands.logout import LogoutHandler
from aiskra.modules.identity.application.commands.onboarding import UpdateOnboardingHandler
from aiskra.modules.identity.application.commands.reset_password import ResetPasswordHandler
from aiskra.modules.identity.application.commands.set_user_blocked import SetUserBlockedHandler
from aiskra.modules.identity.application.commands.update_user import UpdateUserHandler
from aiskra.modules.identity.application.ports.auth import AuthPolicy
from aiskra.modules.identity.application.queries.list_users import ListUsersHandler
from aiskra.modules.identity.application.queries.onboarding import GetOnboardingHandler
from aiskra.modules.identity.application.queries.resolve_session import ResolveSession, ResolveSessionHandler
from aiskra.modules.identity.domain.user import LockoutPolicy
from aiskra.modules.identity.infrastructure.groups import SqlGroupStore
from aiskra.modules.identity.infrastructure.reader import SqlOnboardingReader, SqlSessionReader, SqlUserReader
from aiskra.modules.identity.infrastructure.repositories import SqlSessionRepository, SqlUserRepository
from aiskra.modules.identity.infrastructure.security import ScryptPasswordHasher, SessionTokenIssuer
from aiskra.modules.incidents.api import deps as incidents_deps
from aiskra.modules.incidents.application.commands.add_workout import AddWorkoutHandler
from aiskra.modules.incidents.application.commands.append_card import AppendCardHandler
from aiskra.modules.incidents.application.commands.card_timer import SetCardTimerPausedHandler
from aiskra.modules.incidents.application.commands.change_card_status import ChangeCardStatusHandler
from aiskra.modules.incidents.application.commands.dds import (
    ChangeServiceStatusHandler,
    MarkServiceReceivedHandler,
    SetDdsTimerPausedHandler,
)
from aiskra.modules.incidents.application.commands.open_card import OpenCardHandler
from aiskra.modules.incidents.application.commands.record_card_view import RecordCardViewHandler
from aiskra.modules.incidents.application.commands.save_card import SaveCardHandler
from aiskra.modules.incidents.application.commands.set_card_flags import SetCardFlagsHandler
from aiskra.modules.incidents.application.queries.dds import (
    GetDdsCardHandler,
    ListDdsBrigadesHandler,
    SearchDdsJournalHandler,
)
from aiskra.modules.incidents.application.queries.get_card import GetCardHandler
from aiskra.modules.incidents.application.queries.search_journal import SearchJournalHandler
from aiskra.modules.incidents.infrastructure.dds import SqlDdsReader, SqlDdsRepository
from aiskra.modules.incidents.infrastructure.reader import SqlCardReader
from aiskra.modules.incidents.infrastructure.repositories import SqlCardRepository
from aiskra.modules.system.api import deps as system_deps
from aiskra.modules.system.application.commands.backups import (
    CreateBackupHandler,
    DailyBackupJob,
    ListBackupsHandler,
    RestoreBackupHandler,
)
from aiskra.modules.system.application.commands.probe_model import ProbeModelHandler
from aiskra.modules.system.application.commands.settings import GetSettingsHandler, UpdateSettingsHandler
from aiskra.modules.system.application.queries.admin import GetAlertsHandler, GetStatusHandler, RecentLogsHandler
from aiskra.modules.system.application.queries.get_ai_config import GetAIConfigHandler
from aiskra.modules.system.infrastructure.settings import SqlSettingsStore
from aiskra.modules.training.api import deps as training_deps
from aiskra.modules.training.application.actors import Actors
from aiskra.modules.training.application.commands.calls import (
    AnswerCallHandler,
    EndCallHandler,
    PauseCallHandler,
    SendReplicaHandler,
    StartDdsCallHandler,
    StartIncomingCallHandler,
)
from aiskra.modules.training.application.commands.materials import (
    DeleteMaterialHandler,
    UpdateMaterialHandler,
    UploadMaterialHandler,
)
from aiskra.modules.training.application.commands.scenario_review import ReviewSectionsHandler
from aiskra.modules.training.application.commands.scenarios import (
    EditScenarioHandler,
    GenerateScenariosHandler,
    ReviewScenarioHandler,
    ScenarioGenerator,
    SetScenarioPsyHandler,
)
from aiskra.modules.training.application.commands.sessions import (
    ChangeSessionStateHandler,
    CreateSessionHandler,
    FeedDdsCardHandler,
)
from aiskra.modules.training.application.psy import PsyDirector
from aiskra.modules.training.application.queries.calls import CardCallsHandler, GetCallHandler
from aiskra.modules.training.application.queries.materials import GetMaterialHandler, ListMaterialsHandler
from aiskra.modules.training.application.queries.scenarios import (
    GetScenarioHandler,
    ListScenariosHandler,
    PreviewScenarioHandler,
)
from aiskra.modules.training.application.queries.sessions import (
    GetSessionDefaultsHandler,
    GetSessionHandler,
    ListSessionsHandler,
    ListStudentsHandler,
    MySessionHandler,
    MySessionsHandler,
    SessionMonitorHandler,
)
from aiskra.modules.training.application.speech import (
    CallRecordingHandler,
    ReplicaAudioHandler,
    SpeechStatus,
    TranscribeHandler,
)
from aiskra.modules.training.application.voice_lab import VoiceLab
from aiskra.modules.training.infrastructure.materials import (
    DocumentTextExtractor,
    LocalFileStorage,
    SqlMaterialContext,
    SqlMaterialRepository,
)
from aiskra.modules.training.infrastructure.psy_catalog import YamlPsyCatalog
from aiskra.modules.training.infrastructure.repositories import SqlCallRepository, SqlScenarioRepository
from aiskra.modules.training.infrastructure.sessions import SqlSessionRepository as SqlTrainingSessionRepository
from aiskra.modules.training.infrastructure.sessions import SqlStudentDirectory
from aiskra.platform import logbuffer
from aiskra.platform.backup import FileBackupStore
from aiskra.platform.db import SqlAlchemyUnitOfWork, create_engine, create_session_factory
from aiskra.platform.deps import get_session
from aiskra.platform.models_registry import metadata as _all_models  # noqa: F401 — все ORM-модели в одном реестре
from aiskra.platform.ratelimit import SlidingWindowThrottle
from aiskra.platform.services import Services
from aiskra.platform.settings import Settings
from aiskra.platform.status import SystemStatus
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
        tts=build_tts(ai_config),
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


def build_import_addresses_handler(settings: Settings, session: AsyncSession) -> ImportAddressesHandler:
    return ImportAddressesHandler(
        source=FileAddressSource(settings.dictionaries_dir),
        writer=SqlAddressWriter(session),
        audit=SqlAuditRecorder(session),
        uow=SqlAlchemyUnitOfWork(session),
    )


def _address_query(handler_cls: Callable[[SqlAddressReader], Any]) -> Callable[..., Any]:
    def factory(session: Session) -> Any:
        return handler_cls(SqlAddressReader(session))

    return factory


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


def build_purge_audit_handler(session: AsyncSession) -> PurgeAuditHandler:
    return PurgeAuditHandler(
        SqlAuditPurger(session),
        SystemRetentionPolicy(session),
        SqlAuditRecorder(session),
        SqlAlchemyUnitOfWork(session),
        SystemClock(),
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

    def get_onboarding(session: Session) -> GetOnboardingHandler:
        return GetOnboardingHandler(SqlOnboardingReader(session))

    def update_onboarding(session: Session) -> UpdateOnboardingHandler:
        return UpdateOnboardingHandler(SqlUserRepository(session), SqlAlchemyUnitOfWork(session))

    def purge_audit(session: Session) -> PurgeAuditHandler:
        return build_purge_audit_handler(session)

    def search_audit(session: Session) -> SearchAuditHandler:
        return SearchAuditHandler(SqlAuditReader(session))

    ov[web.provide_principal] = current_principal
    ov[web.provide_isolated_audit] = lambda: IsolatedAuditRecorder(services.session_factory)
    ov[identity_deps.provide_session_cookie] = lambda: ida.cookie
    throttle = SlidingWindowThrottle()
    ov[identity_deps.provide_login_throttle] = lambda: throttle
    ov[identity_deps.provide_login] = login
    ov[identity_deps.provide_logout] = logout
    ov[identity_deps.provide_create_user] = create_user
    ov[identity_deps.provide_update_user] = update_user
    ov[identity_deps.provide_set_user_blocked] = set_blocked
    ov[identity_deps.provide_reset_password] = reset_password
    ov[identity_deps.provide_list_users] = list_users
    ov[identity_deps.provide_get_onboarding] = get_onboarding
    ov[identity_deps.provide_update_onboarding] = update_onboarding
    ov[audit_deps.provide_search_audit] = search_audit
    ov[audit_deps.provide_event_types] = ListEventTypesHandler
    ov[audit_deps.provide_purge] = purge_audit


def _wire_incidents(app: FastAPI) -> None:
    ov = app.dependency_overrides
    clock = SystemClock()

    def open_card(session: Session) -> OpenCardHandler:
        return OpenCardHandler(
            SqlCardRepository(session), SqlAuditRecorder(session), SqlAlchemyUnitOfWork(session), clock
        )

    def save_card(session: Session) -> SaveCardHandler:
        return SaveCardHandler(
            SqlCardRepository(session), SqlAuditRecorder(session), SqlAlchemyUnitOfWork(session), clock
        )

    def get_card(session: Session) -> GetCardHandler:
        return GetCardHandler(SqlCardReader(session))

    ov[incidents_deps.provide_open_card] = open_card
    ov[incidents_deps.provide_save_card] = save_card
    ov[incidents_deps.provide_get_card] = get_card

    # п. 1.3: журнал и работа с сохранённой карточкой
    def journal(session: Session) -> SearchJournalHandler:
        return SearchJournalHandler(SqlCardReader(session))

    def change_status(session: Session) -> ChangeCardStatusHandler:
        return ChangeCardStatusHandler(
            SqlCardRepository(session), SqlAuditRecorder(session), SqlAlchemyUnitOfWork(session), clock
        )

    def set_flags(session: Session) -> SetCardFlagsHandler:
        return SetCardFlagsHandler(SqlCardRepository(session), SqlAuditRecorder(session), SqlAlchemyUnitOfWork(session))

    def card_timer(session: Session) -> SetCardTimerPausedHandler:
        return SetCardTimerPausedHandler(
            SqlCardRepository(session), SqlAuditRecorder(session), SqlAlchemyUnitOfWork(session), clock
        )

    def append(session: Session) -> AppendCardHandler:
        return AppendCardHandler(SqlCardRepository(session), SqlAuditRecorder(session), SqlAlchemyUnitOfWork(session))

    def add_workout(session: Session) -> AddWorkoutHandler:
        return AddWorkoutHandler(
            SqlCardRepository(session), SqlAuditRecorder(session), SqlAlchemyUnitOfWork(session), clock
        )

    def record_view(session: Session) -> RecordCardViewHandler:
        return RecordCardViewHandler(
            SqlCardRepository(session), SqlAuditRecorder(session), SqlAlchemyUnitOfWork(session)
        )

    ov[incidents_deps.provide_search_journal] = journal
    ov[incidents_deps.provide_change_status] = change_status
    ov[incidents_deps.provide_set_flags] = set_flags
    ov[incidents_deps.provide_card_timer] = card_timer
    ov[incidents_deps.provide_append] = append
    ov[incidents_deps.provide_add_workout] = add_workout
    ov[incidents_deps.provide_record_view] = record_view

    # п. 2.1, 2.2: АРМ ДДС
    def dds_received(session: Session) -> MarkServiceReceivedHandler:
        return MarkServiceReceivedHandler(
            SqlDdsRepository(session), SqlAuditRecorder(session), SqlAlchemyUnitOfWork(session), clock
        )

    def dds_status(session: Session) -> ChangeServiceStatusHandler:
        return ChangeServiceStatusHandler(
            SqlDdsRepository(session), SqlAuditRecorder(session), SqlAlchemyUnitOfWork(session), clock
        )

    def dds_timer(session: Session) -> SetDdsTimerPausedHandler:
        return SetDdsTimerPausedHandler(
            SqlDdsRepository(session), SqlAuditRecorder(session), SqlAlchemyUnitOfWork(session), clock
        )

    def dds_journal(session: Session) -> SearchDdsJournalHandler:
        return SearchDdsJournalHandler(SqlDdsReader(session))

    def dds_card(session: Session) -> GetDdsCardHandler:
        return GetDdsCardHandler(SqlCardReader(session))

    def dds_brigades(session: Session) -> ListDdsBrigadesHandler:
        return ListDdsBrigadesHandler(SqlDdsRepository(session))

    ov[incidents_deps.provide_dds_journal] = dds_journal
    ov[incidents_deps.provide_dds_card] = dds_card
    ov[incidents_deps.provide_dds_received] = dds_received
    ov[incidents_deps.provide_dds_status] = dds_status
    ov[incidents_deps.provide_dds_timer] = dds_timer
    ov[incidents_deps.provide_dds_brigades] = dds_brigades


def build_generate_handler(router: ModelRouter, session: AsyncSession) -> GenerateScenariosHandler:
    return GenerateScenariosHandler(
        ScenarioGenerator(DictionaryScenarioFacts(session), router, SqlMaterialContext(session)),
        SqlScenarioRepository(session),
        SqlAuditRecorder(session),
        SqlAlchemyUnitOfWork(session),
    )


def _wire_training(app: FastAPI, services: Services) -> None:
    """п. 3.2, 3.3, 1.4, 2.3: сценарии, ИИ-собеседники, учебные звонки."""
    ov = app.dependency_overrides
    clock = SystemClock()
    router = services.model_router

    catalog = YamlPsyCatalog(services.settings.dictionaries_dir / "psy_profiles.yaml")  # п. 3.7, проверка при старте

    def call_parts(session: AsyncSession) -> tuple[object, ...]:
        return (
            SqlCallRepository(session),
            SqlScenarioRepository(session),
            IncidentCardContext(session),
            Actors(router),
            SqlAlchemyUnitOfWork(session),
            clock,
        )

    def psy_parts(session: AsyncSession) -> dict[str, object]:
        """Психологический модификатор (п. 3.7): ведущий и занятия — чтобы выбрать профиль по настройкам."""
        return {"psy": PsyDirector(catalog, Actors(router)), "sessions": SqlTrainingSessionRepository(session)}

    def generate(session: Session) -> GenerateScenariosHandler:
        return build_generate_handler(router, session)

    def review(session: Session) -> ReviewScenarioHandler:
        return ReviewScenarioHandler(
            SqlScenarioRepository(session), SqlAuditRecorder(session), SqlAlchemyUnitOfWork(session)
        )

    def review_sections(session: Session) -> ReviewSectionsHandler:
        return ReviewSectionsHandler(
            SqlScenarioRepository(session), SqlAuditRecorder(session), SqlAlchemyUnitOfWork(session)
        )

    def list_scenarios(session: Session) -> ListScenariosHandler:
        return ListScenariosHandler(SqlScenarioRepository(session))

    def get_scenario(session: Session) -> GetScenarioHandler:
        return GetScenarioHandler(SqlScenarioRepository(session))

    def incoming(session: Session) -> StartIncomingCallHandler:
        return StartIncomingCallHandler(
            *call_parts(session),
            generator=ScenarioGenerator(DictionaryScenarioFacts(session), router, SqlMaterialContext(session)),
            switches=SystemServiceSwitches(session),
            **psy_parts(session),
        )

    def answer(session: Session) -> AnswerCallHandler:
        return AnswerCallHandler(*call_parts(session), **psy_parts(session))  # type: ignore[arg-type]

    def dds_call(session: Session) -> StartDdsCallHandler:
        return StartDdsCallHandler(*call_parts(session), **psy_parts(session))  # type: ignore[arg-type]

    def replica(session: Session) -> SendReplicaHandler:
        return SendReplicaHandler(*call_parts(session), **psy_parts(session))  # type: ignore[arg-type]

    def end_call(session: Session) -> EndCallHandler:
        return EndCallHandler(*call_parts(session), audit=SqlAuditRecorder(session))

    def pause_call(session: Session) -> PauseCallHandler:
        return PauseCallHandler(*call_parts(session), audit=SqlAuditRecorder(session))

    def set_scenario_psy(session: Session) -> SetScenarioPsyHandler:
        return SetScenarioPsyHandler(
            SqlScenarioRepository(session), catalog, SqlAuditRecorder(session), SqlAlchemyUnitOfWork(session)
        )

    def get_call(session: Session) -> GetCallHandler:
        return GetCallHandler(SqlCallRepository(session))

    def replica_audio(session: Session) -> ReplicaAudioHandler:
        return ReplicaAudioHandler(services.tts, SqlCallRepository(session), SqlScenarioRepository(session))

    def call_recording(session: Session) -> CallRecordingHandler:
        return CallRecordingHandler(services.tts, SqlCallRepository(session), SqlScenarioRepository(session))

    def card_calls(session: Session) -> CardCallsHandler:
        return CardCallsHandler(SqlCallRepository(session))

    ov[training_deps.provide_generate] = generate
    ov[training_deps.provide_review] = review
    ov[training_deps.provide_review_sections] = review_sections
    ov[training_deps.provide_list_scenarios] = list_scenarios
    ov[training_deps.provide_get_scenario] = get_scenario
    ov[training_deps.provide_incoming] = incoming
    ov[training_deps.provide_answer] = answer
    ov[training_deps.provide_dds_call] = dds_call
    ov[training_deps.provide_replica] = replica
    ov[training_deps.provide_transcribe] = lambda: TranscribeHandler(services.stt)  # голосовой ввод (п. 1.4)
    voice_lab = VoiceLab(services.stt, services.tts, services.model_router)  # голосовой полигон (п. 3.6)
    ov[training_deps.provide_voice_lab] = lambda: voice_lab
    # голос собеседника (п. 3.6): сервисы читаются при каждом запросе — адаптер можно подменить в тестах
    ov[training_deps.provide_speech_status] = lambda: SpeechStatus(stt=services.stt.enabled, tts=services.tts.enabled)
    ov[training_deps.provide_end_call] = end_call
    ov[training_deps.provide_pause_call] = pause_call
    ov[training_deps.provide_set_scenario_psy] = set_scenario_psy
    ov[training_deps.provide_psy_catalog] = lambda: catalog
    ov[training_deps.provide_get_call] = get_call
    ov[training_deps.provide_replica_audio] = replica_audio
    ov[training_deps.provide_call_recording] = call_recording
    ov[training_deps.provide_card_calls] = card_calls
    _wire_sessions(app, services)


def _wire_sessions(app: FastAPI, services: Services) -> None:
    """п. 4.1–4.2: правка и прогон сценариев, занятия, поток карточек в ДДС, мониторинг."""
    ov = app.dependency_overrides
    clock = SystemClock()

    def edit(session: Session) -> EditScenarioHandler:
        return EditScenarioHandler(
            SqlScenarioRepository(session),
            services.model_router,
            SqlAuditRecorder(session),
            SqlAlchemyUnitOfWork(session),
        )

    def preview(session: Session) -> PreviewScenarioHandler:
        return PreviewScenarioHandler(SqlScenarioRepository(session))

    def create(session: Session) -> CreateSessionHandler:
        return CreateSessionHandler(
            SqlTrainingSessionRepository(session),
            SqlAuditRecorder(session),
            SqlAlchemyUnitOfWork(session),
            clock,
            defaults=SystemSessionDefaults(session),
            catalog=YamlPsyCatalog(services.settings.dictionaries_dir / "psy_profiles.yaml"),
        )

    def session_defaults(session: Session) -> GetSessionDefaultsHandler:
        return GetSessionDefaultsHandler(SystemSessionDefaults(session))

    def my_sessions(session: Session) -> MySessionsHandler:
        return MySessionsHandler(SqlTrainingSessionRepository(session))

    def state(session: Session) -> ChangeSessionStateHandler:
        return ChangeSessionStateHandler(
            SqlTrainingSessionRepository(session), SqlAuditRecorder(session), SqlAlchemyUnitOfWork(session), clock
        )

    def feed(session: Session) -> FeedDdsCardHandler:
        return FeedDdsCardHandler(
            SqlTrainingSessionRepository(session),
            SqlScenarioRepository(session),
            IncidentSystemCards(session),
            SqlAlchemyUnitOfWork(session),
            clock,
            switches=SystemServiceSwitches(session),
        )

    def list_sessions(session: Session) -> ListSessionsHandler:
        return ListSessionsHandler(SqlTrainingSessionRepository(session), SqlStudentDirectory(session))

    def get_session_(session: Session) -> GetSessionHandler:
        return GetSessionHandler(SqlTrainingSessionRepository(session), SqlStudentDirectory(session))

    def my_session(session: Session) -> MySessionHandler:
        return MySessionHandler(SqlTrainingSessionRepository(session))

    def monitor(session: Session) -> SessionMonitorHandler:
        return SessionMonitorHandler(
            SqlTrainingSessionRepository(session), SqlStudentDirectory(session), SessionProgress(session)
        )

    def students(session: Session) -> ListStudentsHandler:
        return ListStudentsHandler(SqlStudentDirectory(session))

    ov[training_deps.provide_edit_scenario] = edit
    ov[training_deps.provide_preview] = preview
    ov[training_deps.provide_create_session] = create
    ov[training_deps.provide_session_state] = state
    ov[training_deps.provide_feed] = feed
    ov[training_deps.provide_list_sessions] = list_sessions
    ov[training_deps.provide_get_session] = get_session_
    ov[training_deps.provide_my_session] = my_session
    ov[training_deps.provide_monitor] = monitor
    ov[training_deps.provide_students] = students
    ov[training_deps.provide_session_defaults] = session_defaults
    ov[training_deps.provide_my_sessions] = my_sessions
    _wire_materials(app, services)


def build_upload_material_handler(settings: Settings, session: AsyncSession) -> UploadMaterialHandler:
    return UploadMaterialHandler(
        SqlMaterialRepository(session),
        LocalFileStorage(settings.materials_dir),
        DocumentTextExtractor(),
        SqlAuditRecorder(session),
        SqlAlchemyUnitOfWork(session),
        SystemClock(),
    )


def _wire_materials(app: FastAPI, services: Services) -> None:
    """п. 4.4: учебные материалы."""
    ov = app.dependency_overrides
    storage = LocalFileStorage(services.settings.materials_dir)

    def upload(session: Session) -> UploadMaterialHandler:
        return build_upload_material_handler(services.settings, session)

    def update(session: Session) -> UpdateMaterialHandler:
        return UpdateMaterialHandler(
            SqlMaterialRepository(session), SqlAuditRecorder(session), SqlAlchemyUnitOfWork(session)
        )

    def remove(session: Session) -> DeleteMaterialHandler:
        return DeleteMaterialHandler(
            SqlMaterialRepository(session), storage, SqlAuditRecorder(session), SqlAlchemyUnitOfWork(session)
        )

    def list_(session: Session) -> ListMaterialsHandler:
        return ListMaterialsHandler(SqlMaterialRepository(session))

    def get(session: Session) -> GetMaterialHandler:
        return GetMaterialHandler(SqlMaterialRepository(session))

    ov[training_deps.provide_upload_material] = upload
    ov[training_deps.provide_update_material] = update
    ov[training_deps.provide_delete_material] = remove
    ov[training_deps.provide_list_materials] = list_
    ov[training_deps.provide_get_material] = get
    ov[training_deps.provide_material_files] = lambda: storage


def _wire_assessment(app: FastAPI, services: Services) -> None:
    """п. 3.4: автооценка по эталону (правила + ИИ-судья)."""
    ov = app.dependency_overrides

    def assess(session: Session) -> AssessCardHandler:
        return AssessCardHandler(
            IncidentAttempts(session),
            SqlAssessmentRepository(session),
            Judge(services.model_router),
            SqlAuditRecorder(session),
            SqlAlchemyUnitOfWork(session),
            psy_judge=PsyJudge(services.model_router),
        )

    def override(session: Session) -> OverrideAssessmentHandler:
        return OverrideAssessmentHandler(
            SqlAssessmentRepository(session), SqlAuditRecorder(session), SqlAlchemyUnitOfWork(session)
        )

    def report(session: Session) -> GetSessionReportHandler:
        return GetSessionReportHandler(
            SessionFactsReader(session), SqlAssessmentRepository(session), SqlFeedbackStore(session)
        )

    def my_report(session: Session) -> GetMySessionReportHandler:
        return GetMySessionReportHandler(
            SessionFactsReader(session), SqlAssessmentRepository(session), SqlFeedbackStore(session)
        )

    def evaluate_session(session: Session) -> EvaluateSessionHandler:
        return EvaluateSessionHandler(SessionFactsReader(session), assess(session))

    def progress(session: Session) -> MyProgressHandler:
        return MyProgressHandler(SqlAssessmentRepository(session))

    def get(session: Session) -> GetAssessmentHandler:
        return GetAssessmentHandler(SqlAssessmentRepository(session))

    def insights(session: Session) -> GroupInsightsHandler:
        return GroupInsightsHandler(SqlAssessmentRepository(session))

    ov[assessment_deps.provide_assess] = assess
    ov[assessment_deps.provide_get] = get
    ov[assessment_deps.provide_insights] = insights
    ov[assessment_deps.provide_override] = override
    ov[assessment_deps.provide_report] = report
    ov[assessment_deps.provide_my_report] = my_report
    ov[assessment_deps.provide_evaluate_session] = evaluate_session
    ov[assessment_deps.provide_progress] = progress

    # аналитика преподавателя (specs/4.5)
    def norm_report(session: Session) -> NormReportHandler:
        return NormReportHandler(SessionFactsReader(session), SqlAssessmentRepository(session))

    def student_profile(session: Session) -> StudentProfileHandler:
        return StudentProfileHandler(
            SessionFactsReader(session), SqlAssessmentRepository(session), SqlScenarioBank(session)
        )

    def debrief(session: Session) -> SessionDebriefHandler:
        return SessionDebriefHandler(
            SessionFactsReader(session), SqlAssessmentRepository(session), SqlScenarioBank(session)
        )

    def suggest(session: Session) -> SuggestAssignmentHandler:
        return SuggestAssignmentHandler(
            SessionFactsReader(session), SqlAssessmentRepository(session), SqlScenarioBank(session)
        )

    ov[assessment_deps.provide_norm_report] = norm_report
    ov[assessment_deps.provide_student_profile] = student_profile
    ov[assessment_deps.provide_debrief] = debrief
    ov[assessment_deps.provide_suggest] = suggest

    def readiness(session: Session) -> ReadinessHandler:
        return ReadinessHandler(SessionFactsReader(session), SqlAssessmentRepository(session))

    ov[assessment_deps.provide_readiness] = readiness

    def validation(session: Session) -> ValidationHandler:  # п. 3.5
        return ValidationHandler(ScenarioBankCases(session), SqlAssessmentRepository(session))

    ov[assessment_deps.provide_validation] = validation

    # отзыв преподавателя по занятию (specs/4.7)
    def feedback_draft(session: Session) -> DraftFeedbackHandler:
        return DraftFeedbackHandler(
            SessionFactsReader(session),
            SqlAssessmentRepository(session),
            SqlFeedbackStore(session),
            services.model_router,
        )

    def feedback_save(session: Session) -> SaveFeedbackHandler:
        return SaveFeedbackHandler(
            SessionFactsReader(session),
            SqlAssessmentRepository(session),
            SqlFeedbackStore(session),
            SqlAuditRecorder(session),
            SqlAlchemyUnitOfWork(session),
        )

    def my_feedback(session: Session) -> MyFeedbackHandler:
        return MyFeedbackHandler(SqlFeedbackStore(session))

    ov[assessment_deps.provide_feedback_draft] = feedback_draft
    ov[assessment_deps.provide_feedback_save] = feedback_save
    ov[assessment_deps.provide_my_feedback] = my_feedback


def _wire_admin(app: FastAPI, services: Services) -> None:
    """п. 5.2: группы, настройки, резервные копии, состояние сервисов, логи."""
    ov = app.dependency_overrides
    backups = FileBackupStore(services.engine, services.settings.backup_dir)
    status = SystemStatus(services, backups)
    logs = logbuffer.install()

    def save_group(session: Session) -> SaveGroupHandler:
        return SaveGroupHandler(SqlGroupStore(session), SqlAuditRecorder(session), SqlAlchemyUnitOfWork(session))

    def delete_group(session: Session) -> DeleteGroupHandler:
        return DeleteGroupHandler(SqlGroupStore(session), SqlAuditRecorder(session), SqlAlchemyUnitOfWork(session))

    def list_groups(session: Session) -> IdentityListGroupsHandler:
        return IdentityListGroupsHandler(SqlGroupStore(session))

    def get_settings(session: Session) -> GetSettingsHandler:
        return GetSettingsHandler(SqlSettingsStore(session))

    def update_settings(session: Session) -> UpdateSettingsHandler:
        return UpdateSettingsHandler(
            SqlSettingsStore(session), SqlAuditRecorder(session), SqlAlchemyUnitOfWork(session)
        )

    def create_backup(session: Session) -> CreateBackupHandler:
        return CreateBackupHandler(backups, SqlSettingsStore(session), IsolatedAuditRecorder(services.session_factory))

    def restore_backup() -> RestoreBackupHandler:
        return RestoreBackupHandler(backups, IsolatedAuditRecorder(services.session_factory))

    ov[identity_deps.provide_save_group] = save_group
    ov[identity_deps.provide_delete_group] = delete_group
    ov[identity_deps.provide_list_groups] = list_groups
    ov[system_deps.provide_get_settings] = get_settings
    ov[system_deps.provide_update_settings] = update_settings
    ov[system_deps.provide_create_backup] = create_backup
    ov[system_deps.provide_restore_backup] = restore_backup
    ov[system_deps.provide_list_backups] = lambda: ListBackupsHandler(backups)
    ov[system_deps.provide_backup_file] = lambda: backups
    ov[system_deps.provide_status] = lambda: GetStatusHandler(status)
    ov[system_deps.provide_logs] = lambda: RecentLogsHandler(logs)
    ov[system_deps.provide_alerts] = lambda: GetAlertsHandler(status, logs)  # п. 10.6


async def daily_backup_loop(services: Services, period_s: float = 60.0) -> None:
    """Встроенный ежедневный запуск резервного копирования (п. 10.5): раз в минуту — «не пора ли?»."""
    log = logging.getLogger("aiskra.backup")
    backups = FileBackupStore(services.engine, services.settings.backup_dir)
    while True:
        await asyncio.sleep(period_s)
        try:
            async with services.session_factory() as session:
                job = DailyBackupJob(
                    backups, SqlSettingsStore(session), IsolatedAuditRecorder(services.session_factory)
                )
                info = await job.tick(datetime.now(UTC))
            if info:
                log.info("ежедневная резервная копия %s: таблиц %s, строк %s", info.name, info.tables, info.rows)
        except Exception:  # сбой копии не должен останавливать приложение — он виден в логе и состоянии сервисов
            log.exception("ежедневная резервная копия не создана")


def wire(app: FastAPI, services: Services) -> None:
    ov = app.dependency_overrides
    _wire_admin(app, services)
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
    ov[dict_deps.provide_list_groups] = _dict_query(ListGroupsHandler)
    ov[dict_deps.provide_list_territory] = _dict_query(ListTerritoryHandler)
    ov[dict_deps.provide_list_enum] = _dict_query(ListEnumHandler)
    subordination = load_subordination(str(services.settings.dictionaries_dir / "subordination.yaml"))

    def resolve_factory(session: Session) -> ResolveServicesHandler:
        return ResolveServicesHandler(SqlDictionaryReader(session), subordination)

    ov[dict_deps.provide_resolve_services] = resolve_factory

    # --- адресный справочник и карта (п. 1.2)
    def import_addresses_factory(session: Session) -> ImportAddressesHandler:
        return build_import_addresses_handler(services.settings, session)

    ov[dict_deps.provide_import_addresses] = import_addresses_factory
    ov[dict_deps.provide_suggest_addresses] = _address_query(SuggestAddressesHandler)
    ov[dict_deps.provide_reverse_geocode] = _address_query(ReverseGeocodeHandler)
    ov[dict_deps.provide_houses_in_box] = _address_query(HousesInBoxHandler)
    ov[dict_deps.provide_district_shapes] = _address_query(DistrictShapesHandler)

    # --- identity и audit (п. 0.3)
    _wire_identity_and_audit(app, services)
    # --- incidents: карточка 112 (п. 1.1)
    _wire_incidents(app)
    # --- training: сценарии, ИИ-собеседники, учебные звонки (п. 3.2, 3.3, 1.4, 2.3)
    _wire_training(app, services)
    # --- assessment: автооценка (п. 3.4)
    _wire_assessment(app, services)
    # --- сюда добавляются связывания модулей training, assessment … (п. 3.x, 4.x)
