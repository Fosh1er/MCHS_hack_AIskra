"""Каталог психологических профилей из YAML (п. 3.7). Файл проверяется при первом чтении: ошибка в каталоге —
отказ с понятным сообщением, а не молчаливо «кривой» заявитель на занятии. Реестр источников (F4) — там же:
каждый код из `sources` профиля обязан в нём быть."""

from __future__ import annotations

from functools import cache
from pathlib import Path

import yaml

from aiskra.modules.training.domain.psy import PsyCatalogError, PsyProfile, parse_catalog
from aiskra.modules.training.domain.psy_methodology import SourceRegistry, check_sources, parse_sources


@cache
def _load(path: str) -> tuple[int, dict[str, PsyProfile], SourceRegistry]:
    p = Path(path)
    if not p.exists():
        raise PsyCatalogError(f"Нет каталога профилей: {p}")
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    version, profiles = parse_catalog(raw)
    registry = parse_sources(raw)
    for profile in profiles.values():
        check_sources(profile.sources, registry, f"профиль {profile.id}, sources")
    return version, profiles, registry


class YamlPsyCatalog:
    def __init__(self, path: Path) -> None:
        self._version, self._profiles, self._registry = _load(str(path))

    @property
    def version(self) -> int:
        return self._version

    def profiles(self) -> dict[str, PsyProfile]:
        return dict(self._profiles)

    def get(self, profile_id: str) -> PsyProfile | None:
        return self._profiles.get(profile_id)

    def registry(self) -> SourceRegistry:
        return self._registry
