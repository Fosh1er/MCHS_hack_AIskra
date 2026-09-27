"""Достоверность автооценки (п. 3.5, specs/3.5-validation.md): бенчмарк мутаций и согласие с экспертом.

**Бенчмарк мутаций.** Для каждого утверждённого сценария строится карточка, заполненная точно по эталону, и её
копии с одной известной ошибкой — такой, какую делают операторы: не тот тип, пропущена основная служба, не тот дом,
не отмечены пострадавшие, превышено время. Для работы ДДС — то же по истории статусов. Меряем:

- *чувствительность* — ошибка найдена: целевой критерий < 1 и есть замечание;
- *специфичность* — на верной карточке нет ни одного замечания и балл 100;
- *локализация* — снизился только целевой критерий, остальные проверяемые не задеты;
- *согласие вердикта* — «зачтено / не зачтено» автооценки против ожидаемого по критичности ошибки: критические
  (обучающийся отправил бы не те силы или не туда — тип другой группы, нет основной службы, не та улица, пропущены
  пострадавшие; у ДДС — неверное решение, решение позже трёх нормативов) → «не зачтено», остальные → «зачтено».
  Считаются доля совпадений и κ Коэна.

**Согласие с экспертом.** По экспертным правкам преподавателя (автобалл до правки и балл эксперта): средняя
абсолютная ошибка балла (MAE), совпадение вердикта и κ Коэна. Это главная метрика на реальных данных; бенчмарк —
проверка, что правила ловят то, что должны.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from aiskra.modules.assessment.domain.scoring import (
    CARD_NORM_SECONDS,
    DDS_NORM_SECONDS,
    INTERVIEW_TOPICS,
    PASS_THRESHOLD,
    TITLES,
    WEIGHTS_112,
    WEIGHTS_DDS,
    StatusStep,
    assess_card_112,
    assess_dds,
    finish,
    norm_words,
)

# ------------------------------------------------------------------ правильная попытка по эталону


def perfect_card(ref: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Карточка 112, заполненная точно по эталону сценария, и её службы."""
    a = ref.get("address") or {}
    data = {
        "card_types": list(ref.get("card_types") or []),
        "incident_types": list(ref.get("incident_types") or []),
        "questionnaire": copy.deepcopy(ref.get("questionnaire") or {}),
        "card_flags": list(ref.get("card_flags") or []),
        "applicant": dict(ref.get("applicant") or {}),
        "victims": dict(ref.get("victims") or {}),
        "address": {k: a.get(k) or "" for k in ("street", "house", "building", "structure", "okrug", "district")},
        "description": " ".join(ref.get("description_keywords") or []) + ". Заявитель сообщает о происшествии.",
    }
    return data, [s["code"] for s in ref.get("services", [])]


def perfect_dds(start: datetime) -> tuple[list[StatusStep], datetime, list[str]]:
    """Работа ДДС по эталону: решение за 10 с, номер наряда, полная цепочка с комментариями, звонок старшему."""
    t = start
    steps = [StatusStep("added", t, None, None), StatusStep("received", t + timedelta(seconds=3), None, None)]
    for i, (status, comment) in enumerate(
        [
            ("accepted", "Сообщение принято, дежурная бригада направлена на место"),
            ("response_started", "Наряд выехал"),
            ("arrived", "Наряд прибыл на место"),
            ("works_in_progress", "Работы начаты"),
            ("works_completed", "Работы завершены"),
        ]
    ):
        steps.append(StatusStep(status, t + timedelta(seconds=10 + 120 * i), "21" if i == 0 else None, comment))
    return steps, t, ["brigade"]


# ------------------------------------------------------------------ мутации


@dataclass(frozen=True)
class Attempt112:
    data: dict[str, Any]
    services: list[str]
    processing_s: float = 40.0
    asked: frozenset[str] = frozenset(INTERVIEW_TOPICS)


@dataclass(frozen=True)
class Mutation:
    key: str
    title: str
    target: str  # критерий, который должен снизиться
    critical: bool  # ожидаемый вердикт — «не зачтено»
    apply: Callable[[Attempt112, dict[str, Any]], Attempt112 | None]  # None — к этому эталону неприменима


def _with(a: Attempt112, **kw: Any) -> Attempt112:
    return Attempt112(**{**a.__dict__, **kw})


def _data(a: Attempt112, fn: Callable[[dict[str, Any]], None]) -> Attempt112:
    d = copy.deepcopy(a.data)
    fn(d)
    return _with(a, data=d)


def _other_group_type(ref: dict[str, Any]) -> str:
    code = str((ref.get("incident_types") or ["00000000"])[0])
    return ("99" if not code.startswith("99") else "98") + code[2:]


def _same_group_type(ref: dict[str, Any]) -> str:
    code = str((ref.get("incident_types") or ["00000000"])[0])
    return code[:-2] + ("99" if not code.endswith("99") else "98")


def _main(ref: dict[str, Any]) -> str | None:
    return next((s["code"] for s in ref.get("services", []) if s.get("main")), None)


MUTATIONS_112: list[Mutation] = [
    Mutation(
        "type_other_group",
        "Тип из другой группы классификатора",
        "type",
        True,
        lambda a, r: _data(a, lambda d: d.update(incident_types=[_other_group_type(r)], card_types=["999"])),
    ),
    Mutation(
        "type_same_group",
        "Близкий тип той же группы",
        "type",
        False,
        lambda a, r: _data(a, lambda d: d.update(incident_types=[_same_group_type(r)])),
    ),
    Mutation(
        "no_main_service",
        "Не направлено в основную службу",
        "services",
        True,
        lambda a, r: _with(a, services=[s for s in a.services if s != _main(r)]) if _main(r) else None,
    ),
    Mutation(
        "no_secondary_service",
        "Пропущена одна из дополнительных служб",
        "services",
        False,
        lambda a, r: (
            _with(a, services=[s for s in a.services if s != extra[0]])
            if (extra := [s["code"] for s in r.get("services", []) if not s.get("main")])
            else None
        ),
    ),
    Mutation(
        "extra_service",
        "Лишняя служба",
        "services",
        False,
        lambda a, r: _with(a, services=[*a.services, "S_EXTRA"]),
    ),
    Mutation(
        "wrong_street",
        "Не та улица",
        "address",
        True,
        lambda a, r: _data(a, lambda d: d["address"].update(street="Проверочная улица")),
    ),
    Mutation(
        "wrong_house",
        "Не тот дом",
        "address",
        False,
        lambda a, r: _data(a, lambda d: d["address"].update(house=(d["address"].get("house") or "0") + "9")),
    ),
    Mutation(
        "no_district",
        "Не указан район",
        "address",
        False,
        lambda a, r: _data(a, lambda d: d["address"].update(district="")),
    ),
    Mutation(
        "missed_flag",
        "Не отмечен признак опросной карты",
        "flags",
        False,
        lambda a, r: _data(a, lambda d: d.update(card_flags=d["card_flags"][1:])) if a.data["card_flags"] else None,
    ),
    Mutation(
        "no_applicant_name",
        "Не записано ФИО заявителя",
        "applicant",
        False,
        lambda a, r: _data(a, lambda d: d["applicant"].update(name="")),
    ),
    Mutation(
        "missed_victims",
        "Не отмечены пострадавшие",
        "victims",
        True,
        lambda a, r: (
            _data(a, lambda d: d.update(victims={"has": False, "count": 0})) if a.data["victims"].get("has") else None
        ),
    ),
    Mutation(
        "victims_count",
        "Неверное число пострадавших",
        "victims",
        False,
        lambda a, r: (
            _data(a, lambda d: d["victims"].update(count=int(d["victims"].get("count") or 0) + 1))
            if a.data["victims"].get("has")
            else None
        ),
    ),
    Mutation(
        "empty_description",
        "Пустое описание со слов заявителя",
        "description",
        False,
        lambda a, r: _data(a, lambda d: d.update(description="")) if r.get("description_keywords") else None,
    ),
    Mutation(
        "no_victims_question",
        "Не спросил о пострадавших",
        "interview",
        False,
        lambda a, r: _with(a, asked=frozenset(INTERVIEW_TOPICS) - {"victims"}),
    ),
    Mutation(
        "slow",
        "Карточка заполнена за два норматива",
        "timing",
        False,
        lambda a, r: _with(a, processing_s=2 * CARD_NORM_SECONDS),
    ),
]


def speech_of(legend: dict[str, Any]) -> str:
    """Что говорит заявитель по легенде — как в продукте (`legend_text` попытки)."""
    return (
        " ".join(str(legend.get(k) or "") for k in ("opening", "what", "details"))
        + " "
        + str(legend.get("facts") or "")
    )


def assess_112(
    a: Attempt112, ref: dict[str, Any], spoken: str | None = None
) -> tuple[float, bool, dict[str, float | None], dict[str, int]]:
    """Балл, вердикт, баллы и число замечаний по критериям — те же функции, что в продукте."""
    criteria = assess_card_112(a.data, a.services, a.processing_s, ref, set(a.asked), spoken=spoken)
    r = finish("112", criteria, WEIGHTS_112, True, PASS_THRESHOLD)
    return r.score, r.passed, {c.key: c.score for c in criteria}, {c.key: len(c.errors) for c in criteria}


@dataclass(frozen=True)
class DdsMutation:
    key: str
    title: str
    target: str
    critical: bool
    apply: Callable[[list[StatusStep], datetime, list[str]], tuple[list[StatusStep], list[str]]]


def _shift_from(steps: list[StatusStep], seconds: float) -> list[StatusStep]:
    """Решение и всё после него — на `seconds` позже."""
    out, moved = [], False
    for s in steps:
        moved = moved or s.status not in ("added", "received")
        out.append(
            StatusStep(s.status, s.at + timedelta(seconds=seconds) if moved and s.at else s.at, s.order_no, s.comment)
        )
    return out


MUTATIONS_DDS: list[DdsMutation] = [
    DdsMutation(
        "rejected",
        "«Не принята» вместо «Принята»",
        "decision",
        True,
        lambda st, t0, calls: ([*st[:2], StatusStep("rejected", st[2].at, None, "Не наша зона")], calls),
    ),
    DdsMutation(
        "very_slow",
        "Решение позже трёх нормативов",
        "reaction",
        True,
        lambda st, t0, calls: (_shift_from(st, 3.5 * DDS_NORM_SECONDS), calls),
    ),
    DdsMutation(
        "slow", "Решение за полтора норматива", "reaction", False, lambda st, t0, calls: (_shift_from(st, 35), calls)
    ),
    DdsMutation(
        "no_order_no",
        "Не указан номер наряда",
        "order_no",
        False,
        lambda st, t0, calls: (
            [s if s.status != "accepted" else StatusStep(s.status, s.at, None, s.comment) for s in st],
            calls,
        ),
    ),
    DdsMutation(
        "no_comments",
        "Статусы без комментариев",
        "comments",
        False,
        lambda st, t0, calls: ([StatusStep(s.status, s.at, s.order_no, None) for s in st], calls),
    ),
    DdsMutation(
        "chain_incomplete",
        "Работы не доведены до «Работы завершены»",
        "chain",
        False,
        lambda st, t0, calls: (st[:4], calls),
    ),
    DdsMutation("no_call", "Нет звонка старшему группы", "calls", False, lambda st, t0, calls: (st, [])),
]


def assess_dds_attempt(
    steps: list[StatusStep], added: datetime, ref: dict[str, Any], calls: list[str]
) -> tuple[float, bool, dict[str, float | None], dict[str, int]]:
    criteria = assess_dds(steps, added, ref, calls)
    r = finish("dds", criteria, WEIGHTS_DDS, True, PASS_THRESHOLD)
    return r.score, r.passed, {c.key: c.score for c in criteria}, {c.key: len(c.errors) for c in criteria}


@dataclass(frozen=True)
class ScenarioCase:
    legend: dict[str, Any]
    reference: dict[str, Any]
    reference_dds: dict[str, Any]
    routed: set[str] | None  # службы автоподбора по текущему классификатору; None — не пересчитывались


# ------------------------------------------------------------------ метрики


def cohen_kappa(pairs: list[tuple[bool, bool]]) -> float | None:
    """κ Коэна для двух разметчиков «зачтено / не зачтено»; None — нет данных или разметка вырождена."""
    n = len(pairs)
    if not n:
        return None
    po = sum(a == b for a, b in pairs) / n
    pa, pb = sum(a for a, _ in pairs) / n, sum(b for _, b in pairs) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return None if pe >= 1 else round((po - pe) / (1 - pe), 3)


@dataclass
class MutationStat:
    key: str
    title: str
    role: str
    target: str
    target_title: str
    critical: bool
    cases: int = 0
    detected: int = 0
    localized: int = 0
    verdict_ok: int = 0
    scores: list[float] = field(default_factory=list)

    def row(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "role": self.role,
            "target": self.target_title,
            "critical": self.critical,
            "cases": self.cases,
            "detection": round(self.detected / self.cases, 3) if self.cases else None,
            "localization": round(self.localized / self.cases, 3) if self.cases else None,
            "verdict_agreement": round(self.verdict_ok / self.cases, 3) if self.cases else None,
            "avg_score": round(sum(self.scores) / len(self.scores), 1) if self.scores else None,
        }


@dataclass(frozen=True)
class Benchmark:
    scenarios: int
    cases: int
    specificity_112: float | None  # доля верных карточек без замечаний и с баллом 100
    specificity_dds: float | None
    detection: float | None  # по всем мутациям
    localization: float | None
    verdict_accuracy: float | None
    verdict_kappa: float | None
    critical_caught: float | None  # доля критических ошибок с вердиктом «не зачтено»
    mutations: list[dict[str, Any]]


def _collect(
    stat: MutationStat,
    before: dict[str, float | None],
    after: dict[str, float | None],
    errs: dict[str, int],
    score: float,
    passed: bool,
    pairs: list[tuple[bool, bool]],
) -> None:
    stat.cases += 1
    t = stat.target
    got = after.get(t)
    detected = got is not None and got < 1 and errs.get(t, 0) > 0
    stat.detected += detected
    others = [
        k for k in before if k != t and k in after
    ]  # не проверялся после ошибки (цепочка после отказа) — не в счёт
    stat.localized += detected and all((after.get(k) or 0) >= (before.get(k) or 0) for k in others)
    expected_pass = not stat.critical
    stat.verdict_ok += passed == expected_pass
    stat.scores.append(score)
    pairs.append((expected_pass, passed))


def run_benchmark(cases: list[ScenarioCase]) -> Benchmark:
    """`cases` — утверждённые сценарии: легенда, эталон карточки, эталон ДДС."""
    stats112 = {
        m.key: MutationStat(m.key, m.title, "112", m.target, TITLES.get(m.target, m.target), m.critical)
        for m in MUTATIONS_112
    }
    stats_dds = {
        m.key: MutationStat(m.key, m.title, "dds", m.target, TITLES.get(m.target, m.target), m.critical)
        for m in MUTATIONS_DDS
    }
    pairs: list[tuple[bool, bool]] = []
    clean112, clean_dds = [], []
    t0 = datetime(2026, 9, 29, 10, 0, tzinfo=UTC)
    for case in cases:
        ref, ref_dds, spoken = case.reference, case.reference_dds, speech_of(case.legend)
        data, services = perfect_card(ref)
        base = Attempt112(data, services)
        score, passed, before, errs = assess_112(base, ref, spoken)
        clean112.append(score == 100 and not any(errs.values()))
        pairs.append((True, passed))
        for m in MUTATIONS_112:
            mutated = m.apply(base, ref)
            if mutated is None:
                continue
            s, p, after, e = assess_112(mutated, ref, spoken)
            _collect(stats112[m.key], before, after, e, s, p, pairs)
        steps, added, calls = perfect_dds(t0)
        score, passed, before_d, errs_d = assess_dds_attempt(steps, added, ref_dds, calls)
        clean_dds.append(score == 100 and not any(errs_d.values()))
        pairs.append((True, passed))
        for dm in MUTATIONS_DDS:
            st, cl = dm.apply(steps, added, calls)
            s, p, after, e = assess_dds_attempt(st, added, ref_dds, cl)
            _collect(stats_dds[dm.key], before_d, after, e, s, p, pairs)
    all_stats = [st for st in [*stats112.values(), *stats_dds.values()] if st.cases]
    total_cases = sum(st.cases for st in all_stats)
    crit = [st for st in all_stats if st.critical]
    crit_cases = sum(st.cases for st in crit)

    def share(xs: list[bool]) -> float | None:
        return round(sum(xs) / len(xs), 3) if xs else None

    def per_case(n: int) -> float | None:
        return round(n / total_cases, 3) if total_cases else None

    return Benchmark(
        scenarios=len(cases),
        cases=total_cases,
        specificity_112=share(clean112),
        specificity_dds=share(clean_dds),
        detection=per_case(sum(st.detected for st in all_stats)),
        localization=per_case(sum(st.localized for st in all_stats)),
        verdict_accuracy=share([a == b for a, b in pairs]),
        verdict_kappa=cohen_kappa(pairs),
        critical_caught=round(sum(st.verdict_ok for st in crit) / crit_cases, 3) if crit_cases else None,
        mutations=[st.row() for st in all_stats],
    )


@dataclass(frozen=True)
class ExpertAgreement:
    """Автооценка против экспертной правки преподавателя (по последней версии оценки каждой карточки)."""

    pairs: int
    mae: float | None  # средняя абсолютная разница баллов
    verdict_agreement: float | None
    kappa: float | None
    threshold: float = PASS_THRESHOLD


def expert_agreement(pairs: list[tuple[float, float]], threshold: float = PASS_THRESHOLD) -> ExpertAgreement:
    """`pairs` — (автобалл, балл эксперта)."""
    if not pairs:
        return ExpertAgreement(0, None, None, None, threshold)
    verdicts = [(e >= threshold, a >= threshold) for a, e in pairs]
    return ExpertAgreement(
        pairs=len(pairs),
        mae=round(sum(abs(a - e) for a, e in pairs) / len(pairs), 1),
        verdict_agreement=round(sum(x == y for x, y in verdicts) / len(verdicts), 3),
        kappa=cohen_kappa(verdicts),
        threshold=threshold,
    )


# ------------------------------------------------------------------ генератор: легенда против эталона


GENERATOR_CHECKS = {
    "address": "Адрес легенды = адрес эталона",
    "victims": "Пострадавшие легенды = эталон",
    "applicant": "Заявитель легенды = эталон",
    "keywords": "Ключевые факты эталона есть в речи заявителя",
    "routing": "Службы эталона = автоподбор по классификатору",
    "main_service": "У эталона есть основная служба (графа «главная служба» классификатора)",
}


def generator_checks(case: ScenarioCase) -> dict[str, bool | None]:
    """Согласованность сценария: то, что скажет заявитель, и то, что считается правильным ответом."""
    leg, ref = case.legend, case.reference
    la, ra = leg.get("address") or {}, ref.get("address") or {}
    speech = norm_words(speech_of(leg))
    words = [w for w in ref.get("description_keywords") or [] if w]
    main = next((s["code"] for s in ref.get("services", []) if s.get("main")), None)
    return {
        "address": all(norm_words(la.get(k)) == norm_words(ra.get(k)) for k in ("street", "house", "district")),
        "victims": bool((leg.get("victims") or {}).get("has")) == bool((ref.get("victims") or {}).get("has"))
        and int((leg.get("victims") or {}).get("count") or 0) == int((ref.get("victims") or {}).get("count") or 0),
        "applicant": (leg.get("applicant") or {}).get("name") == (ref.get("applicant") or {}).get("name")
        and (leg.get("applicant") or {}).get("status") == (ref.get("applicant") or {}).get("status"),
        "keywords": (sum(norm_words(w)[:5] in speech for w in words) / len(words) >= 0.5) if words else None,
        "routing": {s["code"] for s in ref.get("services", [])} == case.routed if case.routed is not None else None,
        "main_service": main is not None,
    }


def generator_summary(cases: list[ScenarioCase]) -> list[dict[str, Any]]:
    per: dict[str, list[bool]] = {k: [] for k in GENERATOR_CHECKS}
    for case in cases:
        for k, v in generator_checks(case).items():
            if v is not None:
                per[k].append(v)
    return [
        {"key": k, "title": GENERATOR_CHECKS[k], "checked": len(v), "share": round(sum(v) / len(v), 3) if v else None}
        for k, v in per.items()
    ]
