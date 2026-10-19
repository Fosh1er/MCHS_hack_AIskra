"""Проверка настроек при запуске (F6.3, ADR-0015): в prod небезопасный запуск отклоняется сразу.

- prod — каждая найденная проблема останавливает запуск; сообщение по-русски перечисляет все проблемы и как их
  исправить (fail fast, а не тихая работа с паролем по умолчанию);
- demo и dev — те же проблемы только пишутся в лог предупреждениями.

Что проверяется (коды — в сообщении и в тестах):
- `cookie_insecure` — cookie сессии без `Secure` (`AISKRA_SESSION_COOKIE_SECURE`). Единственное допустимое
  переопределение — учебный контур без TLS: `AISKRA_PROD_ALLOW_HTTP=true` (предупреждение при каждом запуске);
- `db_password` — пароль БД пустой или известный по умолчанию (`aiskra`, `postgres`, …);
- `admin_password` — пароль начального администратора (`AISKRA_BOOTSTRAP_ADMIN_PASSWORD`) известный или слабый;
- `external_ai` — в конфиге ИИ `allow_external: true`, а в окружении нет явного `AISKRA_AI_ALLOW_EXTERNAL=true`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from aiskra.ai.config import AIConfig
from aiskra.platform.settings import Settings
from aiskra.shared.errors import ConfigError

log = logging.getLogger("aiskra.startup")

# Пароли, которые встречаются в примерах, документации и по умолчанию у образов: в prod их быть не должно.
DEFAULT_DB_PASSWORDS = frozenset({"", "aiskra", "postgres", "password", "changeme", "secret"})
KNOWN_ADMIN_PASSWORDS = frozenset(
    {
        "admin",
        "administrator",
        "password",
        "changeme",
        "aiskra",
        "12345678",
        "123456789",
        "1234567890",
        "qwerty123",
        "qwertyuiop",
        "admin12345",
        "admin123456",
        "password123",
    }
)
ADMIN_PASSWORD_MIN = 12  # в prod строже общего правила (8 символов): учётка с полным доступом
ADMIN_PASSWORD_CLASSES = 3  # из четырёх: строчные, прописные, цифры, прочие символы


@dataclass(frozen=True)
class Problem:
    code: str
    message: str


class UnsafeConfigError(ConfigError):
    """Запуск в prod с небезопасными настройками (F6.3). Сообщение — для администратора контура."""

    code = "unsafe_config"


def weak_admin_password(password: str, *, login: str, demo_password: str | None = None) -> str | None:
    """Почему пароль администратора слабый (или None, если подходит для prod)."""
    lowered = password.strip().lower()
    if lowered in KNOWN_ADMIN_PASSWORDS or (demo_password and password == demo_password):
        return "известный пароль (из примеров или совпадает с паролем демо-учёток)"
    if login and login.strip().lower() in lowered:
        return "содержит логин"
    if len(password) < ADMIN_PASSWORD_MIN:
        return f"короче {ADMIN_PASSWORD_MIN} символов"
    classes = sum(
        (
            any(c.islower() for c in password),
            any(c.isupper() for c in password),
            any(c.isdigit() for c in password),
            any(not c.isalnum() for c in password),
        )
    )
    if classes < ADMIN_PASSWORD_CLASSES:
        return f"нужны символы хотя бы {ADMIN_PASSWORD_CLASSES} видов из 4: строчные, прописные буквы, цифры, знаки"
    return None


def _db_password(database_url: str) -> str | None:
    """Пароль из адреса БД; None — БД без пароля по своей природе (SQLite)."""
    try:
        url = make_url(database_url)
    except ArgumentError:
        return None  # некорректный адрес покажет само подключение к БД
    if url.get_backend_name() == "sqlite":
        return None
    return url.password if isinstance(url.password, str) else ""


def find_problems(settings: Settings, ai: AIConfig) -> list[Problem]:
    problems: list[Problem] = []
    if not settings.session_cookie_secure and not settings.prod_allow_http:
        problems.append(
            Problem(
                "cookie_insecure",
                "cookie сессии без флага Secure — задайте AISKRA_SESSION_COOKIE_SECURE=true и откройте вход по HTTPS "
                "(в docker compose это уже так). Учебный контур без TLS: AISKRA_PROD_ALLOW_HTTP=true",
            )
        )
    db_password = _db_password(settings.database_url)
    if db_password is not None and db_password.strip().lower() in DEFAULT_DB_PASSWORDS:
        problems.append(
            Problem(
                "db_password",
                "пароль БД пустой или по умолчанию — задайте свой POSTGRES_PASSWORD в .env "
                "(его же docker compose подставит в AISKRA_DATABASE_URL)",
            )
        )
    if settings.bootstrap_admin_password is not None:
        demo = settings.demo_password.get_secret_value() if settings.demo_password else None
        reason = weak_admin_password(
            settings.bootstrap_admin_password.get_secret_value(),
            login=settings.bootstrap_admin_login,
            demo_password=demo,
        )
        if reason:
            problems.append(
                Problem(
                    "admin_password",
                    f"пароль администратора AISKRA_BOOTSTRAP_ADMIN_PASSWORD слабый: {reason}. Нужно не короче "
                    f"{ADMIN_PASSWORD_MIN} символов, без логина и известных паролей",
                )
            )
    if ai.allow_external and not settings.ai_allow_external:
        problems.append(
            Problem(
                "external_ai",
                "в конфиге ИИ включено allow_external (внешние адреса моделей), а явного разрешения нет — "
                "задайте AISKRA_AI_ALLOW_EXTERNAL=true или выключите allow_external в конфиге ИИ",
            )
        )
    return problems


def check_startup(settings: Settings, ai: AIConfig) -> list[Problem]:
    """В prod — отказ запуска при любой проблеме; в demo и dev — предупреждения. Возвращает найденные проблемы."""
    problems = find_problems(settings, ai)
    if settings.app_env == "prod":
        if problems:
            lines = "\n".join(f"  • [{p.code}] {p.message}" for p in problems)
            message = (
                "Запуск в режиме prod (AISKRA_APP_ENV=prod) отклонён — небезопасные настройки:\n"
                f"{lines}\n"
                "Исправьте .env и перезапустите. Для демонстрационного стенда — AISKRA_APP_ENV=demo (ADR-0015)."
            )
            raise UnsafeConfigError(message)
        if settings.prod_allow_http and not settings.session_cookie_secure:
            log.warning(
                "prod: cookie сессии без Secure разрешена переменной AISKRA_PROD_ALLOW_HTTP — только для учебного "
                "контура без TLS в закрытой сети"
            )
        if ai.default_provider == "fake":
            log.info("prod: модели не подключены — ИИ-собеседники и генерация работают в офлайн-режиме")
        return problems
    for p in problems:
        log.warning("режим %s: %s [%s] — в prod запуск был бы отклонён", settings.app_env, p.message, p.code)
    return problems
