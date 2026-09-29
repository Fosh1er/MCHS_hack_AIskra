"""Порт каталога психологических профилей (п. 3.7): источник — data/dictionaries/psy_profiles.yaml."""

from __future__ import annotations

from typing import Protocol

from aiskra.modules.training.domain.psy import PsyProfile


class PsyCatalog(Protocol):
    @property
    def version(self) -> int: ...

    def profiles(self) -> dict[str, PsyProfile]: ...

    def get(self, profile_id: str) -> PsyProfile | None: ...
