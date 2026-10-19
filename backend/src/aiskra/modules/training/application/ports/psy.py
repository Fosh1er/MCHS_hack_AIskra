"""Порт каталога психологических профилей (п. 3.7): источник — data/dictionaries/psy_profiles.yaml."""

from __future__ import annotations

from typing import Protocol

from aiskra.modules.training.domain.psy import PsyProfile
from aiskra.modules.training.domain.psy_methodology import SourceRegistry


class PsyCatalog(Protocol):
    @property
    def version(self) -> int: ...

    def profiles(self) -> dict[str, PsyProfile]: ...

    def get(self, profile_id: str) -> PsyProfile | None: ...


class PsyMethodologySource(Protocol):
    """Каталог вместе с реестром источников — для страницы «Методика» (F4)."""

    @property
    def version(self) -> int: ...

    def profiles(self) -> dict[str, PsyProfile]: ...

    def registry(self) -> SourceRegistry: ...
