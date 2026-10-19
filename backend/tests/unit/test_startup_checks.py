"""F6.3 (ADR-0015): проверка настроек при запуске — в prod небезопасный запуск отклоняется с понятным сообщением,
в demo и dev — только предупреждения; уровень логов в prod не подробнее INFO."""

import logging

import pytest
from pydantic import SecretStr

from aiskra.ai.config import AIConfig, ProviderConfig
from aiskra.cli import check_config
from aiskra.platform.settings import Settings
from aiskra.platform.startup_checks import UnsafeConfigError, check_startup, find_problems, weak_admin_password

STRONG = "Смена-112-Пульт!"  # синтетический пароль только для тестов
SAFE = {
    "app_env": "prod",
    "session_cookie_secure": True,
    "database_url": "postgresql+asyncpg://aiskra:Db-Pass-Strong-2026@db:5432/aiskra",
    "bootstrap_admin_password": SecretStr(STRONG),
    "ai_config_path": "/nonexistent/ai.yaml",
}
OFFLINE = AIConfig()
EXTERNAL = AIConfig(
    allow_external=True,
    default_provider="ext",
    providers={"ext": ProviderConfig(kind="openai_compatible", base_url="https://api.example.com/v1")},
)


def make(**kw: object) -> Settings:
    return Settings.model_validate({**SAFE, **kw})


def codes(settings: Settings, ai: AIConfig = OFFLINE) -> set[str]:
    return {p.code for p in find_problems(settings, ai)}


def test_safe_prod_starts() -> None:
    assert check_startup(make(), OFFLINE) == []


@pytest.mark.parametrize(
    ("change", "code", "hint"),
    [
        ({"session_cookie_secure": False}, "cookie_insecure", "AISKRA_SESSION_COOKIE_SECURE=true"),
        ({"database_url": "postgresql+asyncpg://aiskra:aiskra@db:5432/aiskra"}, "db_password", "POSTGRES_PASSWORD"),
        ({"database_url": "postgresql+asyncpg://aiskra@db:5432/aiskra"}, "db_password", "POSTGRES_PASSWORD"),
        ({"database_url": "postgresql+asyncpg://aiskra:@db:5432/aiskra"}, "db_password", "POSTGRES_PASSWORD"),
        ({"bootstrap_admin_password": SecretStr("admin12345")}, "admin_password", "известный пароль"),
        ({"bootstrap_admin_password": SecretStr("Короткий-1")}, "admin_password", "короче 12 символов"),
        ({"bootstrap_admin_password": SecretStr("admin-Strong-2026")}, "admin_password", "содержит логин"),
        ({"bootstrap_admin_password": SecretStr("всестрочныебуквы")}, "admin_password", "3 видов из 4"),
    ],
)
def test_prod_refuses_unsafe_settings(change: dict[str, object], code: str, hint: str) -> None:
    with pytest.raises(UnsafeConfigError) as exc:
        check_startup(make(**change), OFFLINE)
    message = exc.value.message
    assert message.startswith("Запуск в режиме prod (AISKRA_APP_ENV=prod) отклонён")
    assert f"[{code}]" in message and hint in message
    assert STRONG not in message and "Db-Pass-Strong-2026" not in message  # секреты в сообщение не попадают


def test_all_problems_listed_at_once() -> None:
    unsafe = make(
        session_cookie_secure=False,
        database_url="postgresql+asyncpg://aiskra:aiskra@db/aiskra",
        bootstrap_admin_password=SecretStr("password"),
    )
    assert codes(unsafe, EXTERNAL) == {"cookie_insecure", "db_password", "admin_password", "external_ai"}


def test_external_ai_needs_explicit_variable() -> None:
    with pytest.raises(UnsafeConfigError, match="AISKRA_AI_ALLOW_EXTERNAL=true"):
        check_startup(make(), EXTERNAL)
    assert check_startup(make(ai_allow_external=True), EXTERNAL) == []
    assert codes(make(ai_allow_external=True), OFFLINE) == set()  # переменная без внешней модели — не проблема


def test_admin_password_equal_to_demo_password_is_weak() -> None:
    assert weak_admin_password(STRONG, login="admin", demo_password=STRONG)
    assert weak_admin_password(STRONG, login="admin", demo_password="другой") is None


def test_no_bootstrap_password_and_sqlite_are_not_checked() -> None:
    """Администратор создан заранее (`create-user`) — пароля в окружении нет, проверять нечего; у SQLite пароля нет."""
    assert codes(make(bootstrap_admin_password=None, database_url="sqlite+aiosqlite:///./x.db")) == set()


def test_training_contour_without_tls_override(caplog: pytest.LogCaptureFixture) -> None:
    """Единственное переопределение: учебный контур prod без TLS — cookie без Secure, с предупреждением в лог."""
    with caplog.at_level(logging.WARNING, logger="aiskra.startup"):
        assert check_startup(make(session_cookie_secure=False, prod_allow_http=True), OFFLINE) == []
    assert "AISKRA_PROD_ALLOW_HTTP" in caplog.text
    with pytest.raises(UnsafeConfigError, match="db_password"):  # пароли переопределением не обойти
        check_startup(
            make(session_cookie_secure=False, prod_allow_http=True, database_url="postgresql://aiskra:aiskra@db/a"),
            OFFLINE,
        )


@pytest.mark.parametrize("env", ["demo", "dev"])
def test_demo_and_dev_only_warn(env: str, caplog: pytest.LogCaptureFixture) -> None:
    unsafe = make(app_env=env, session_cookie_secure=False, database_url="postgresql://aiskra:aiskra@db/aiskra")
    with caplog.at_level(logging.WARNING, logger="aiskra.startup"):
        found = check_startup(unsafe, EXTERNAL)
    assert {p.code for p in found} == {"cookie_insecure", "db_password", "external_ai"}
    assert caplog.text.count("в prod запуск был бы отклонён") == 3


def test_cli_check_config_uses_same_rules() -> None:
    with pytest.raises(UnsafeConfigError, match="cookie_insecure"):
        check_config(make(session_cookie_secure=False))
    check_config(make())


def test_prod_log_level_not_below_info() -> None:
    assert make(log_level="DEBUG").effective_log_level == logging.INFO
    assert make(log_level="warning").effective_log_level == logging.WARNING
    assert make(app_env="dev", log_level="DEBUG").effective_log_level == logging.DEBUG
    assert make(app_env="prod", log_level="нет такого").effective_log_level == logging.INFO
