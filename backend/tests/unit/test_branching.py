"""F5: ветвящиеся сценарии — каталог шаблонов, граф, детерминированный движок, разбор развилок.

Бенчмарк в духе мутаций (техспека F5 §5.5): перебираем ходы звонка (какая инструкция и когда сказана, когда сохранена
карточка) и проверяем, что каждый узел и каждый итог достижимы, а каждая развилка меняет итог."""

import itertools
from dataclasses import replace
from pathlib import Path

import pytest

from aiskra.modules.training.domain.branching import (
    OUTCOMES,
    BranchTemplateError,
    Facts,
    Template,
    detect,
    entered,
    forks,
    from_snapshot,
    initial_state,
    outcome_of,
    parse_catalog,
    parse_template,
    resolve,
    validate_graph,
)
from aiskra.modules.training.infrastructure.branch_catalog import YamlBranchCatalog

CATALOG = YamlBranchCatalog(Path(__file__).parents[3] / "data" / "dictionaries" / "branch_templates.yaml")
TEMPLATES = CATALOG.templates()
TIMES = (None, 30.0, 100.0, 150.0, 250.0)  # инструкция не сказана / сразу / позже / после первой беды / поздно
CARDS = (None, 80.0, 300.0)  # карточка не сохранена / вовремя / поздно


def _services(t: Template) -> frozenset[str]:
    return frozenset(e.when.service for n in t.nodes.values() for e in n.edges if e.when.service)


def _runs(t: Template) -> list[tuple[Facts, list[str], str]]:
    """Все комбинации решений: факты, пройденный путь, итог."""
    ids = list(t.instructions)
    out = []
    for said_times in itertools.product(TIMES, repeat=len(ids)):
        for card in CARDS:
            facts = Facts(
                said={i: s for i, s in zip(ids, said_times, strict=True) if s is not None},
                asked={"address": 15.0},
                card_saved_s=card,
                services=_services(t) if card else frozenset(),
            )
            state = resolve(t, facts, t.horizon_s)
            o = outcome_of(t, state)
            assert o is not None, f"{t.id}: ход без итога {facts}"
            out.append((facts, state.visited, o.code))
    return out


def test_catalog_is_valid_and_sized() -> None:
    assert set(TEMPLATES) == {"fire_flat", "cardiac_arrest", "gas_leak", "dtp_victims"}
    for t in TEMPLATES.values():
        assert validate_graph(t) == []
        assert 3 <= len(t.forks) <= 5, t.id  # техспека F5 §5.2: 3–5 развилок
        assert 3 <= len({n.outcome.code for n in t.terminals if n.outcome}) <= 4, t.id  # 3–4 итога
        assert t.incident_codes and t.legend.get("opening")
        for n in t.nodes.values():
            for e in n.edges:
                assert t.sources[e.source].url.startswith("http"), (t.id, n.id)  # у каждого перехода — источник
        for i in t.instructions.values():
            assert t.sources[i.source].url.startswith("http")


@pytest.mark.parametrize("tid", sorted(TEMPLATES))
def test_template_checks(tid: str) -> None:
    """Контрольные ходы из шаблона: идеальный оператор, типичная ошибка, худший случай."""
    t = TEMPLATES[tid]
    assert len(t.checks) >= 3
    got = {c.name: outcome_of(t, resolve(t, c.facts, t.horizon_s)) for c in t.checks}
    assert {name: o.code if o else None for name, o in got.items()} == {c.name: c.expect for c in t.checks}
    assert {o.code for o in got.values() if o} >= {"favorable", "adverse"}


def _without(facts: Facts, edge_when: object) -> Facts:
    """Мутация: убрать решение, по которому сработал переход (инструкцию или сохранение карточки)."""
    said = getattr(edge_when, "said", None)
    if said is not None:
        return replace(facts, said={k: v for k, v in facts.said.items() if k != said})
    return replace(facts, card_saved_s=None, services=frozenset())


@pytest.mark.parametrize("tid", sorted(TEMPLATES))
def test_every_node_and_outcome_reachable_and_forks_matter(tid: str) -> None:
    t = TEMPLATES[tid]
    runs = _runs(t)
    visited = {n for _, path, _ in runs for n in path}
    assert visited == set(t.nodes), f"не достигнуты: {set(t.nodes) - visited}"
    reached = {code for _, _, code in runs}
    assert reached == {n.outcome.code for n in t.terminals if n.outcome}
    for fork in t.forks:
        taken = {path[path.index(fork.id) + 1] for _, path, _ in runs if fork.id in path[:-1]}
        assert taken == {e.to for e in fork.edges}, f"{fork.id}: не все переходы достижимы {taken}"
        # мутация: на развилке сработало решение оператора — без него итог другой хотя бы в одном ходе звонка
        decisions = [e for e in fork.edges if not e.when.timed_only]
        changed = False
        for facts, path, code in runs:
            if fork.id not in path[:-1]:
                continue
            nxt = path[path.index(fork.id) + 1]
            for e in decisions:
                if e.to == nxt:
                    mutated = outcome_of(t, resolve(t, _without(facts, e.when), t.horizon_s))
                    changed = changed or (mutated is not None and mutated.code != code)
        assert changed, f"{fork.id}: решение на развилке не меняет итог"


def test_same_facts_same_path_and_live_equals_replay() -> None:
    """Пересчёт по ходу звонка (по репликам) совпадает с пересчётом целиком: путь — чистая функция ходов."""
    t = TEMPLATES["fire_flat"]
    full = Facts(said={"evacuate": 70.0}, asked={"address": 20.0}, card_saved_s=95.0, services=frozenset({"S101"}))
    once = resolve(t, full, t.horizon_s)
    assert once == resolve(t, full, t.horizon_s)
    live = initial_state(t)
    for now, facts in (
        (20.0, Facts(asked={"address": 20.0})),
        (70.0, Facts(said={"evacuate": 70.0}, asked={"address": 20.0})),
        (t.horizon_s, full),
    ):
        live = resolve(t, facts, now, live)
    assert live.path == once.path and once.visited == ["start", "out", "contained"]


def test_time_edges_fire_at_their_moment_not_later() -> None:
    """Порог времени срабатывает в свой момент, даже если следующий факт пришёл позже: адрес на 70-й секунде не
    отменяет того, что на 40-й заявительница уже пошла к выключателю."""
    t = TEMPLATES["gas_leak"]
    s = resolve(t, Facts(said={"no_light": 60.0}), 60.0)
    assert [(p.node, p.at_s) for p in s.path] == [("start", 0.0), ("about_light", 40.0), ("safe", 60.0)]
    assert entered(initial_state(t), s) == ["about_light", "safe"]


def test_detect_instructions_with_negation() -> None:
    fire, gas, dtp = TEMPLATES["fire_flat"], TEMPLATES["gas_leak"], TEMPLATES["dtp_victims"]
    assert detect(fire, "Выходите из квартиры, закройте за собой дверь, лифтом не пользуйтесь!") == ["evacuate"]
    assert detect(fire, "Откройте окна, проветрите") == ["open_window"]
    assert detect(fire, "Не открывайте окна!") == []
    assert set(detect(gas, "Не включайте свет и перекройте газ")) == {"safety", "no_light"}
    assert detect(dtp, "Не вытаскивайте его, прижмите рану") == ["first_aid"]
    assert detect(dtp, "Вытащите его из машины") == ["pull_out"]


def test_forks_debrief_taken_and_alternatives() -> None:
    t = TEMPLATES["cardiac_arrest"]
    s = resolve(t, Facts(said={"wrong_aid": 30.0}, asked={"address": 10.0}), t.horizon_s)
    f = forks(t, s)
    assert [x.node for x in f] == ["start", "wrong", "no_cpr"]
    start = f[0]
    assert start.taken is not None and start.taken.to == "wrong" and start.decided_s == 30.0
    assert {c.to for c in start.others} == {"cpr", "no_breath"}
    assert all(c.source.url for c in start.others)
    assert outcome_of(t, s) is not None and outcome_of(t, s).code == "tragic"  # type: ignore[union-attr]


def test_validator_catches_broken_graphs() -> None:
    sources = {"s": {"title": "Источник", "url": "https://example.org"}}
    edge = {"label": "л", "effect": "э", "source": "s"}
    raw = {
        "title": "Битый",
        "start": "a",
        "instructions": {"x": {"title": "т", "stems": ["икс"], "source": "s"}},
        "nodes": {
            "a": {"title": "А", "edges": [{**edge, "to": "b", "when": {"said": "x"}}]},  # нет перехода по времени
            "b": {"title": "Б", "edges": [{**edge, "to": "a", "when": {"said": "x"}}]},  # цикл без времени
            "c": {"title": "В", "outcome": {"code": "favorable", "text": "т", "sources": ["s"]}},  # недостижим
        },
    }
    errors = validate_graph(parse_template("broken", raw, sources))
    assert any("нет перехода по времени" in e for e in errors)
    raw["nodes"]["a"]["edges"].append({**edge, "to": "c", "when": {"after_s": 10}})
    raw["nodes"]["b"]["edges"].append({**edge, "to": "c", "when": {"after_s": 10}})
    errors = validate_graph(parse_template("broken", raw, sources))
    assert any("цикл без перехода по времени" in e for e in errors)
    with pytest.raises(BranchTemplateError):
        parse_catalog({"sources": sources, "templates": {"broken": raw}})
    with pytest.raises(BranchTemplateError):
        parse_template(
            "bad", {**raw, "nodes": {"a": {"title": "А", "edges": [{**edge, "to": "c", "when": {"x": 1}}]}}}, sources
        )


def test_snapshot_copy_is_self_contained() -> None:
    snap = CATALOG.snapshot("fire_flat", {"address": {"floor": 5, "label": "Тверская улица, 7"}})
    assert "checks" not in snap and set(snap["sources"]) <= set(CATALOG.templates()["fire_flat"].sources)
    t = from_snapshot(snap)
    assert validate_graph(t) == [] and t.id == "fire_flat"
    assert set(OUTCOMES) >= {n.outcome.code for n in t.terminals if n.outcome}


def test_model_rewords_only_event_lines_and_facts_are_checked() -> None:
    """RF5-09: модель переписывает реплики-события под легенду; новая цифра или номер службы — отказ, остаётся
    текст шаблона. Структура графа не меняется."""
    import asyncio
    import random

    from aiskra.ai.adapters.fake import FakeLLM
    from aiskra.ai.router import ModelRouter, TaskProfile
    from aiskra.ai.tasks import AITask
    from aiskra.modules.training.application.commands.scenarios import ScenarioGenerator, check_event_text
    from tests.unit.test_training_ai import ADDR
    from tests.unit.test_training_ai import Facts as DictFacts

    texts = {
        "trapped": "Мы заперты, в коридоре дым стеной, сын кашляет!",
        "out": "Вышли на 9 этаж, дверь закрыли!",  # 9 нет ни в реплике, ни в легенде — отказ
        "sheltered": "Позвоните 101!",  # номер службы — отказ
    }
    llm = FakeLLM(name="demo", fixtures={AITask.BRANCH_TEXTS: {"texts": texts}})
    tasks = [AITask.SCENARIO_GENERATION, AITask.BRANCH_TEXTS]
    router = ModelRouter(
        profiles={t: TaskProfile(task=t, provider="demo") for t in tasks},
        clients={"demo": llm},
        default_provider="demo",
    )
    gen = ScenarioGenerator(DictFacts(), router, branches=CATALOG)
    s = asyncio.run(gen.generate(random.Random(1), [], 2, None, branching="fire_flat"))
    assert s.branching is not None and s.branching["id"] == "fire_flat"
    nodes = s.branching["nodes"]
    assert nodes["trapped"]["event"] == texts["trapped"]
    assert nodes["out"]["event"] == TEMPLATES["fire_flat"].nodes["out"].event
    assert nodes["sheltered"]["event"] == TEMPLATES["fire_flat"].nodes["sheltered"].event
    assert validate_graph(from_snapshot(s.branching)) == []  # граф после правки текстов прежний
    assert s.legend["opening"] == TEMPLATES["fire_flat"].legend["opening"] and s.legend["victims"]["has"] is False
    assert s.reference_card["victims"]["has"] is False and ADDR.street in s.legend["address"]["label"]
    assert check_event_text("Дым уже в коридоре!", "Дым в коридоре", {}) is None
    assert check_event_text("[плачет] Дым!", "Дым", {}) == "ремарки"
