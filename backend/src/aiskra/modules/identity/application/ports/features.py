"""Включённые возможности тренажёра — из настроек администратора (через `integration/`, модули не импортируют
друг друга). Сейчас одна: роль оператора 112 (`services.role_112`, по рекомендациям экспертов скрыта по умолчанию)."""

from __future__ import annotations

from typing import Protocol

FEATURES = ("role_112",)


class FeatureSwitches(Protocol):
    async def enabled(self, name: str) -> bool: ...


async def features_of(switches: FeatureSwitches | None) -> dict[str, bool]:
    """Флаги для интерфейса; без порта (тесты, CLI) — всё включено, как было до выключателя."""
    if switches is None:
        return dict.fromkeys(FEATURES, True)
    return {name: await switches.enabled(name) for name in FEATURES}
