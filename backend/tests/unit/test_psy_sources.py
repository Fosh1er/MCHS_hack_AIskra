"""F4 «Психологический профиль — на первый план»: реестр источников, основания критериев, карточки «Методики»,
сводка «типичные ошибки работы со стрессом». Сверка с каталогом и с файлами docs/research/psychology."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from aiskra.modules.assessment.application.queries.psy_basis import GetPsyBasis, PsyBasisHandler
from aiskra.modules.assessment.domain.psy_scoring import (
    ACT_SOURCES,
    CRITERIA_BASIS,
    FORBIDDEN_ACTS,
    FORBIDDEN_TITLES,
    WEIGHTS_PSY,
    WHY,
    PsyAttempt,
    PsyTurn,
    stress_errors,
    timeline,
)
from aiskra.modules.training.application.queries.psy_methodology import GetPsyMethodology, PsyMethodologyHandler
from aiskra.modules.training.domain.psy import ACT_TITLES, BAD_ACTS, PsyCatalogError
from aiskra.modules.training.domain.psy_methodology import parse_sources, profile_card
from aiskra.modules.training.infrastructure.psy_catalog import YamlPsyCatalog

ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "data" / "dictionaries" / "psy_profiles.yaml"
RESEARCH = ROOT / "docs" / "research" / "psychology"
CATALOG = YamlPsyCatalog(CATALOG_PATH)
REGISTRY = CATALOG.registry()


def _heading_exists(doc: str, section: str) -> bool:
    text = (RESEARCH / doc).read_text(encoding="utf-8")
    return re.search(rf"^### {re.escape(section)}\. ", text, re.M) is not None


def test_every_source_code_resolves_to_registry_and_research_section() -> None:
    used = {c for p in CATALOG.profiles().values() for c in p.sources}
    used |= {c.source for b in CRITERIA_BASIS.values() for c in b.cites}
    used |= {c.source for cs in ACT_SOURCES.values() for c in cs}
    assert used <= set(REGISTRY.sources), f"нет в реестре: {used - set(REGISTRY.sources)}"
    for s in REGISTRY.sources.values():
        assert _heading_exists(s.doc, s.section), f"{s.code}: нет раздела «### {s.section}.» в {s.doc}"
        assert s.url is None or s.url.startswith("https://")


def test_basis_lists_official_sources_only() -> None:
    codes = [b.source for b in REGISTRY.basis]
    # ЦЭПП 2023/2012, профстандарт 12.002, Минздрав 2025, ПП № 1931, ECCS IAED, APCO/NENA
    assert {"РФ-1", "РФ-2", "РФ-13", "РФ-6", "РФ-10", "М-0.1", "М-1.1"} <= set(codes)
    assert all(REGISTRY.sources[c].official and b.use for c, b in zip(codes, REGISTRY.basis, strict=True))
    assert "681н" in REGISTRY.sources["РФ-13"].title and "1931" in REGISTRY.sources["РФ-10"].short


def test_no_affiliation_claims_in_texts() -> None:
    """Только официальные источники: ни слова об участии вузов (техспека F4, ограничение по формулировкам)."""
    raw = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))
    texts = [str(v) for s in raw["sources"].values() for k, v in s.items() if k != "url"]
    texts += [b["use"] for b in raw["basis"]] + [b.why for b in CRITERIA_BASIS.values()]
    assert not [t for t in texts if re.search(r"МГУ|психолог\w* (МГУ|вуза)|разработан\w* психолог", t)]


def test_registry_validation() -> None:
    with pytest.raises(PsyCatalogError, match="нужны short и title"):
        parse_sources({"sources": {"РФ-1": {"short": "x"}}})
    with pytest.raises(PsyCatalogError, match="РФ-N"):
        parse_sources({"sources": {"X-1": {"short": "x", "title": "y"}}})
    with pytest.raises(PsyCatalogError, match="не официальный"):
        parse_sources({"sources": {"РФ-3": {"short": "x", "title": "y"}}, "basis": [{"source": "РФ-3"}]})
    with pytest.raises(PsyCatalogError, match="https"):
        parse_sources({"sources": {"РФ-3": {"short": "x", "title": "y", "url": "http://a"}}})


def test_criteria_and_acts_have_basis() -> None:
    assert set(CRITERIA_BASIS) == set(WEIGHTS_PSY)
    assert all(b.why and b.cites for b in CRITERIA_BASIS.values())
    assert set(ACT_SOURCES) == set(WHY)
    # запрещённые действия отчёта — те же коды и названия, что в движке (модули друг друга не импортируют)
    assert FORBIDDEN_ACTS == BAD_ACTS
    assert {c: ACT_TITLES[c] for c in BAD_ACTS} == FORBIDDEN_TITLES
    view = asyncio.run(PsyBasisHandler()(GetPsyBasis()))
    assert {r.key for r in view.criteria} == set(WEIGHTS_PSY) and {r.key for r in view.acts} == set(WHY)


def test_profile_card_from_catalog() -> None:
    panic = profile_card(CATALOG.profiles()["panic"])
    assert [s.level for s in panic.signs] == [5, 4, 3, 2, 1] and panic.signs[0].title == "неуправляем"
    keys = [a.code for a in panic.does if a.key]
    assert set(keys) == set(CATALOG.profiles()["panic"].key_acts) and panic.does[0].key
    assert panic.donts[0].code == "THREAT_HANGUP" and panic.donts[0].critical  # критичные — первыми
    assert {a.title for a in panic.donts} >= {"«успокойтесь», «возьмите себя в руки»"}
    stupor = profile_card(CATALOG.profiles()["stupor"])
    assert stupor.routing == ["подключить психолога", "добавить в карточку службу S103 или CEMP"]
    suicidal = profile_card(CATALOG.profiles()["suicidal"])
    assert any(a.code == "HANGUP_FIRST" and a.critical for a in suicidal.donts)  # событие из critical, не из hurts


def test_methodology_has_every_profile_and_its_sources() -> None:
    view = asyncio.run(PsyMethodologyHandler(CATALOG)(GetPsyMethodology()))
    assert [p.id for p in view.profiles] == list(CATALOG.profiles())
    for card in view.profiles:
        assert card.sources == list(CATALOG.profiles()[card.id].sources)
        assert all(code in view.sources for code in card.sources)
    assert len(view.basis) == len(REGISTRY.basis) and view.scale[0].title == "спокоен"


def _block(*codes_per_turn: tuple[str, ...], paused: bool = False) -> dict[str, Any]:
    if paused:
        return {"paused": True, "note": "пауза"}
    turns = [PsyTurn("operator", "реплика", float(i), acts=codes) for i, codes in enumerate(codes_per_turn)]
    return {"timeline": timeline(PsyAttempt(profile={}, turns=turns, ended_by=None, services=[]))}


def test_stress_errors_top_by_frequency_with_sources() -> None:
    blocks = [
        ("a", _block(("CALM_DOWN", "GREET"), ("CALM_DOWN",), ("RUDE",))),
        ("b", _block(("CALM_DOWN",), ("JARGON",), ("REASK_KNOWN",))),  # REASK_KNOWN — событие, не BAD_ACTS
        ("b", _block(("JARGON",), ("ARGUE",), ("TRIGGER_WORD",), ("BLAME",))),
        ("c", _block(paused=True)),  # «пауза» — блок не оценивался
    ]
    r = stress_errors(blocks)
    assert r.calls == 3
    assert [e.code for e in r.items][:2] == ["CALM_DOWN", "JARGON"] and len(r.items) == 5
    calm = r.items[0]
    assert (calm.count, calm.calls, calm.students) == (3, 2, 2)
    assert calm.title == FORBIDDEN_TITLES["CALM_DOWN"] and calm.why == WHY["CALM_DOWN"]
    assert {s["source"] for s in calm.sources} == {"РФ-1", "РФ-6"}
    jargon = r.items[1]
    assert (jargon.count, jargon.calls, jargon.students) == (2, 2, 1)
    assert stress_errors([]).items == [] and stress_errors([]).calls == 0


def test_timeline_marks_source_only_for_mistakes() -> None:
    items = _block(("GREET", "CALM_DOWN"))["timeline"][0]["acts"]
    by = {a["code"]: a for a in items}
    assert by["GREET"]["sources"] == [] and by["CALM_DOWN"]["sources"][0]["source"] == "РФ-1"
