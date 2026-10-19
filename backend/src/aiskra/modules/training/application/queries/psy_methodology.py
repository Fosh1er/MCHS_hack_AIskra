"""Запрос «Методика» (F4, RF4-03): научно-методическая основа модификатора и 15 профилей заявителя карточками.

Ответ собирается из каталога `psy_profiles.yaml` (профили, реестр источников, перечень основы) — без копий текста
во фронтенде. Читать могут все роли: преподаватель — в кабинете, обучающийся — в справочной базе.
"""

from __future__ import annotations

from dataclasses import dataclass

from aiskra.modules.training.application.ports.psy import PsyMethodologySource
from aiskra.modules.training.domain.psy import LEVEL_TITLES
from aiskra.modules.training.domain.psy_methodology import ProfileCard, PsySource, profile_card
from aiskra.shared.application import Query


@dataclass(frozen=True, kw_only=True)
class GetPsyMethodology(Query):
    pass


@dataclass(frozen=True)
class SourceView:
    code: str
    short: str
    title: str
    url: str | None
    official: bool
    doc: str  # файл исследования в docs/research/psychology
    section: str  # раздел в нём


@dataclass(frozen=True)
class BasisView:
    source: SourceView
    use: str


@dataclass(frozen=True)
class ScaleLevel:
    level: int
    title: str


@dataclass(frozen=True)
class MethodologyView:
    version: int
    scale: list[ScaleLevel]
    basis: list[BasisView]
    profiles: list[ProfileCard]
    sources: dict[str, SourceView]


def _view(s: PsySource) -> SourceView:
    return SourceView(
        code=s.code, short=s.short, title=s.title, url=s.url, official=s.official, doc=s.doc, section=s.section
    )


class PsyMethodologyHandler:
    def __init__(self, catalog: PsyMethodologySource) -> None:
        self._catalog = catalog

    async def __call__(self, q: GetPsyMethodology) -> MethodologyView:
        reg = self._catalog.registry()
        sources = {code: _view(s) for code, s in reg.sources.items()}
        return MethodologyView(
            version=self._catalog.version,
            scale=[ScaleLevel(level=lv, title=t) for lv, t in sorted(LEVEL_TITLES.items())],
            basis=[BasisView(source=sources[b.source], use=b.use) for b in reg.basis],
            profiles=[profile_card(p) for p in self._catalog.profiles().values()],
            sources=sources,
        )
