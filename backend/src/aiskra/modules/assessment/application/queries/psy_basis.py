"""Основания блока «Работа с заявителем» (F4, RF4-02): почему важен каждый критерий и откуда запрет каждого
действия. Те же данные пишутся в `details.psy` новых оценок; запрос нужен оценкам, сделанным до F4.
Коды источников раскрывает реестр каталога профилей (`GET /training/psy/methodology`, поле `sources`)."""

from __future__ import annotations

from dataclasses import dataclass

from aiskra.modules.assessment.domain.psy_scoring import (
    ACT_SOURCES,
    ACT_TITLES_SHORT,
    CRITERIA_BASIS,
    FORBIDDEN_TITLES,
    WHY,
    cites,
)
from aiskra.modules.assessment.domain.scoring import TITLES
from aiskra.shared.application import Query


@dataclass(frozen=True, kw_only=True)
class GetPsyBasis(Query):
    pass


@dataclass(frozen=True)
class BasisRow:
    key: str
    title: str
    why: str
    sources: list[dict[str, str]]


@dataclass(frozen=True)
class PsyBasisView:
    criteria: list[BasisRow]
    acts: list[BasisRow]


class PsyBasisHandler:
    async def __call__(self, q: GetPsyBasis) -> PsyBasisView:
        return PsyBasisView(
            criteria=[
                BasisRow(key=k, title=TITLES.get(k, k), why=b.why, sources=cites(b.cites))
                for k, b in CRITERIA_BASIS.items()
            ],
            acts=[
                BasisRow(
                    key=code,
                    title=FORBIDDEN_TITLES.get(code) or ACT_TITLES_SHORT.get(code) or WHY[code].split(" (")[0],
                    why=WHY[code],
                    sources=cites(src),
                )
                for code, src in ACT_SOURCES.items()
            ],
        )
