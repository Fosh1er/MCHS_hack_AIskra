"""Ошибки приложения: что видит пользователь, а что остаётся в журнале."""

from aiskra.shared.errors import DomainError, ExternalServiceError


def test_domain_error_message_is_public() -> None:
    e = DomainError("Пустая запись", code="empty_audio")
    assert e.public_message == "Пустая запись"


def test_external_service_error_hides_details() -> None:
    e = ExternalServiceError("синтез речи недоступен (HTTPStatusError: 402 Payment Required for url https://x)")
    assert "402" in e.message and "402" not in e.public_message
    assert e.public_message == ExternalServiceError.public
    custom = ExternalServiceError("timeout", code="stt_unavailable", public="Напечатайте реплику")
    assert custom.public_message == "Напечатайте реплику" and custom.code == "stt_unavailable"
