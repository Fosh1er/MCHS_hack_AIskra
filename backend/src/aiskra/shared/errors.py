"""Иерархия ошибок приложения. HTTP-коды назначаются в одном месте — aiskra.main."""


class AppError(Exception):
    """Базовая ошибка приложения."""

    code: str = "app_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class DomainError(AppError):
    """Нарушено бизнес-правило (HTTP 422)."""

    code = "domain_error"


class NotFoundError(AppError):
    """Объект не найден (HTTP 404)."""

    code = "not_found"


class AuthenticationError(AppError):
    """Нет действующей сессии или неверные учётные данные (HTTP 401)."""

    code = "unauthenticated"


class PermissionDeniedError(AppError):
    """Недостаточно прав (HTTP 403)."""

    code = "permission_denied"


class ConfigError(AppError):
    """Некорректная конфигурация — приложение не должно стартовать."""

    code = "config_error"


class ExternalServiceError(AppError):
    """Внешний сервис (модель, STT, TTS) недоступен или ответил некорректно (HTTP 503)."""

    code = "external_service_error"
