"""Каталог психологических профилей из YAML (п. 3.7). Файл проверяется при первом чтении: ошибка в каталоге —
отказ с понятным сообщением, а не молчаливо «кривой» заявитель на занятии."""

from __future__ import annotations

from functools import cache
from pathlib import Path

import yaml

from aiskra.modules.training.domain.psy import PsyCatalogError, PsyProfile, parse_catalog


@cache
def _load(path: str) -> tuple[int, dict[str, PsyProfile]]:
    p = Path(path)
    if not p.exists():
        raise PsyCatalogError(f"Нет каталога профилей: {p}")
    return parse_catalog(yaml.safe_load(p.read_text(encoding="utf-8")) or {})


class YamlPsyCatalog:
    def __init__(self, path: Path) -> None:
        self._version, self._profiles = _load(str(path))

    @property
    def version(self) -> int:
        return self._version

    def profiles(self) -> dict[str, PsyProfile]:
        return dict(self._profiles)

    def get(self, profile_id: str) -> PsyProfile | None:
        return self._profiles.get(profile_id)
