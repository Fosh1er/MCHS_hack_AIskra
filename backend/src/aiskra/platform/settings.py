"""Настройки приложения из окружения (префикс AISKRA_). Секреты — только через env."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[4]

AppEnv = Literal["prod", "demo", "dev"]
DEMO_ENVS: frozenset[str] = frozenset({"demo", "dev"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AISKRA_", env_file=".env", extra="ignore")

    # Режим окружения (ADR-0015, F6.3): prod — контур заказчика, demo — публичный стенд, dev — разработка.
    # Демо-вход (F2) есть только в demo и dev. docker compose по умолчанию запускает prod.
    app_env: AppEnv = "dev"
    log_level: str = "INFO"  # в prod не ниже INFO: DEBUG пишет запросы и ответы (effective_log_level)
    # Версия сборки (git sha) для /health: задаётся при сборке образа (ARG AISKRA_VERSION в backend/Dockerfile)
    version: str = "unknown"
    database_url: str = "postgresql+asyncpg://aiskra:aiskra@localhost:5432/aiskra"
    ai_config_path: str = str(_REPO_ROOT / "config" / "ai.yaml")
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:8080"]
    api_prefix: str = "/api/v1"
    data_dir: str = str(_REPO_ROOT / "data")
    backup_dir: str = str(_REPO_ROOT / "var" / "backups")
    materials_dir: str = str(
        _REPO_ROOT / "var" / "materials"
    )  # учебные материалы (п. 4.4); в docker — том materials  # резервные копии (п. 5.2); в docker — том backups

    # Вход и сессии (п. 0.3, ADR-0010)
    session_cookie_name: str = "aiskra_session"
    scheduler_enabled: bool = True  # фоновые задачи: ежедневная копия (п. 10.5); в тестах выключается
    session_cookie_secure: bool = False  # true — в контуре с TLS (docker compose: nginx с HTTPS)
    expose_docs: bool = True  # /docs и /openapi.json; в prod — только вошедшему администратору; false — нигде
    # prod без TLS (учебный контур в закрытой сети): разрешить cookie без Secure. Только осознанно (ADR-0015)
    prod_allow_http: bool = False
    # Явное разрешение внешних моделей: в prod конфиг ИИ с allow_external: true без него не запускается (ADR-0015).
    # Та же переменная подставляется в allow_external в config/ai.openrouter.yaml и ai.example.yaml
    ai_allow_external: bool = False
    session_ttl_hours: int = 24  # автовыход через 24 ч, как в АРМ-112
    login_max_attempts: int = 5
    login_lock_minutes: int = 15
    password_scrypt_n: int = 2**14
    # Начальный администратор: `python -m aiskra.cli ensure-admin` (вызывается при старте контейнера)
    bootstrap_admin_login: str = "admin"
    bootstrap_admin_password: SecretStr | None = None
    bootstrap_admin_name: str = "Администратор системы"
    # Демо-стенд (F2): пароль демо-учёток (тот же, что для `demo-seed`) и показ его на странице входа.
    # Пароль уходит в API только при demo_show_password=true и только в режиме demo/dev.
    demo_password: SecretStr | None = None
    demo_show_password: bool = False

    @field_validator("app_env", mode="before")
    @classmethod
    def _normalize_env(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @property
    def demo_enabled(self) -> bool:
        """Демо-вход и демо-учётки на странице входа (F2): только в режимах demo и dev."""
        return self.app_env in DEMO_ENVS

    @property
    def docs_admin_only(self) -> bool:
        """Swagger и схема API в prod — только вошедшему администратору (F6.3)."""
        return self.app_env == "prod"

    @property
    def effective_log_level(self) -> int:
        """Уровень логов: в prod не подробнее INFO, в demo и dev — как задан."""
        level = logging.getLevelName(self.log_level.strip().upper())
        level = level if isinstance(level, int) else logging.INFO
        return max(level, logging.INFO) if self.app_env == "prod" else level

    @property
    def classifier_path(self) -> Path:
        return Path(self.data_dir) / "source" / "classifier_v046.xlsx"

    @property
    def dictionaries_dir(self) -> Path:
        return Path(self.data_dir) / "dictionaries"
