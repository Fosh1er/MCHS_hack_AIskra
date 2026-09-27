"""Готовность к допуску (specs/4.6): оценка по шкале итогового контроля Программы подготовки дежурно-диспетчерского
персонала ЕДДС (МЧС России, протокол Правкомиссии от 31.10.2023 № 9) по последним карточкам обучающегося.

Шкала программы: «отлично» — 90–100 % и практическая задача выполнена полностью и в срок; «хорошо» — 75–90 %,
в срок; «удовлетворительно» — 60–75 %, с небольшим превышением времени; «неудовлетворительно» — меньше 60 %
или задача не выполнена либо время значительно превышено. Процент — средний балл автооценки (с учётом экспертных
правок), срок — нормативы ПП РФ № 1931 (карточка 75 с, решение ДДС 30 с). Функции чистые.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aiskra.modules.assessment.domain.analytics import percentile

EXCELLENT, GOOD, SATISFACTORY = 90.0, 75.0, 60.0
ON_TIME_SHARE = 0.9  # «в срок»: не меньше 90 % карточек в нормативе
SLIGHT_SHARE, SLIGHT_P90 = 0.6, 1.5  # «небольшое превышение»: ≥ 60 % в нормативе и 90-й процентиль ≤ 1,5 норматива
MIN_CARDS = 5  # меньше — оценку не ставим: «недостаточно данных»


def _cards(n: int) -> str:
    """«1 оценённая карточка», «2 оценённые карточки», «5 оценённых карточек»."""
    m10, m100 = n % 10, n % 100
    if m10 == 1 and m100 != 11:
        return f"{n} оценённая карточка"
    if 2 <= m10 <= 4 and not 12 <= m100 <= 14:
        return f"{n} оценённые карточки"
    return f"{n} оценённых карточек"


GRADES = {5: "отлично", 4: "хорошо", 3: "удовлетворительно", 2: "неудовлетворительно"}


@dataclass(frozen=True)
class Readiness:
    grade: int | None  # 5…2; None — недостаточно данных
    grade_label: str
    ready: bool  # допуск к зачёту: оценка не ниже «удовлетворительно»
    status: str
    cards: int
    avg_score: float | None
    timing: str  # в срок | небольшое превышение | значительное превышение | нет данных
    within_share: float | None
    p90_ratio: float | None  # 90-й процентиль времени к нормативу
    reasons: list[str] = field(default_factory=list)


def timing_class(samples: list[tuple[float, float]]) -> tuple[str, float | None, float | None]:
    """Соблюдение срока по парам (факт, норматив), с."""
    if not samples:
        return "нет данных", None, None
    share = sum(1 for f, n in samples if f <= n) / len(samples)
    ratio = percentile([f / n for f, n in samples if n > 0], 90)
    if share >= ON_TIME_SHARE:
        return "в срок", round(share, 3), ratio
    if share >= SLIGHT_SHARE and ratio is not None and ratio <= SLIGHT_P90:
        return "небольшое превышение", round(share, 3), ratio
    return "значительное превышение", round(share, 3), ratio


def assess_readiness(
    scores: list[float], samples: list[tuple[float, float]], *, min_cards: int = MIN_CARDS
) -> Readiness:
    """`scores` — баллы последних карточек (0–100), `samples` — время тех же карточек и нормативы."""
    timing, share, ratio = timing_class(samples)
    avg = round(sum(scores) / len(scores), 1) if scores else None
    if len(scores) < min_cards or avg is None:
        return Readiness(
            grade=None,
            grade_label="недостаточно данных",
            ready=False,
            status=f"нужна ещё {_cards(min_cards - len(scores))}"
            if min_cards - len(scores) == 1
            else f"нужно ещё {_cards(min_cards - len(scores))}",
            cards=len(scores),
            avg_score=avg,
            timing=timing,
            within_share=share,
            p90_ratio=ratio,
            reasons=[f"оценено {len(scores)} из {min_cards} карточек, нужных для оценки"],
        )
    in_time = timing in ("в срок", "нет данных")  # нет времени (ДДС без решения) — судим по баллу
    slight = timing == "небольшое превышение"
    if avg >= EXCELLENT and in_time:
        grade = 5
    elif avg >= GOOD and in_time:
        grade = 4
    elif avg >= SATISFACTORY and (in_time or slight):
        grade = 3
    else:
        grade = 2
    reasons = [
        f"средний балл {avg:.0f} %",
        f"время: {timing}" + (f", в нормативе {share * 100:.0f} %" if share is not None else ""),
    ]
    if grade == 3 and avg >= GOOD and slight:
        reasons.append("балл на «хорошо», но с превышением времени — по шкале «удовлетворительно»")
    if grade == 2:
        reasons.append(
            "балл ниже 60 %" if avg < SATISFACTORY else "время значительно превышено — по шкале «неудовлетворительно»"
        )
    return Readiness(
        grade=grade,
        grade_label=GRADES[grade],
        ready=grade >= 3,
        status="готов к зачёту" if grade >= 3 else "нужна дополнительная практика",
        cards=len(scores),
        avg_score=avg,
        timing=timing,
        within_share=share,
        p90_ratio=ratio,
        reasons=reasons,
    )
