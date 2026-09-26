"""Внедрение зависимостей без DI-фреймворка (ADR-0004).

API модуля объявляет «заглушку провайдера» — функцию, которая падает, если её не подменили.
Composition root (aiskra.bootstrap) подменяет заглушку реальной фабрикой через
`app.dependency_overrides`. Так слой API знает только типы application-слоя.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")


def provider_stub(name: str) -> Callable[[], Any]:
    """Создать заглушку провайдера зависимости с понятной ошибкой при отсутствии связывания."""

    def _stub() -> Any:
        raise RuntimeError(f"Зависимость «{name}» не связана в composition root (aiskra.bootstrap.wire)")

    _stub.__name__ = f"provide_{name}"
    return _stub
