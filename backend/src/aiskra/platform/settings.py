"""Настройки приложения из окружения (префикс AISKRA_). Секреты — только через env."""

from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AISKRA_", env_file=".env", extra="ignore")

    app_env: str = "dev"
    log_level: str = "INFO"
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
    session_cookie_secure: bool = False  # true — в контуре с TLS
    session_ttl_hours: int = 24  # автовыход через 24 ч, как в АРМ-112
    login_max_attempts: int = 5
    login_lock_minutes: int = 15
    password_scrypt_n: int = 2**14
    # Начальный администратор: `python -m aiskra.cli ensure-admin` (вызывается при старте контейнера)
    bootstrap_admin_login: str = "admin"
    bootstrap_admin_password: SecretStr | None = None
    bootstrap_admin_name: str = "Администратор системы"

    @property
    def classifier_path(self) -> Path:
        return Path(self.data_dir) / "source" / "classifier_v046.xlsx"

    @property
    def dictionaries_dir(self) -> Path:
        return Path(self.data_dir) / "dictionaries"
