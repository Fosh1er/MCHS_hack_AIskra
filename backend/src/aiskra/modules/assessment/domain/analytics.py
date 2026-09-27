"""Аналитика преподавателя: нормативы времени, ошибки, выбор сложности следующего задания.

Нормативы — ПП РФ № 1931, п. 9 «р»: опрос до карточки, доступной ДДС, — в среднем 75 с; подтверждение приёма
карточки в ДДС — не более 30 с (docs/research/Подготовка_персонала_112_и_ЕДДС.md). Функции чистые, без БД.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass


def percentile(values: list[float], p: float) -> float | None:
    """Процентиль с линейной интерполяцией (как в Excel ПРОЦЕНТИЛЬ.ВКЛ); пустой список — None."""
    if not values:
        return None
    xs = sorted(values)
    k = (len(xs) - 1) * p / 100
    lo, hi = math.floor(k), math.ceil(k)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (k - lo), 1)


@dataclass(frozen=True)
class NormStat:
    """«Норматив / факт» по одному показателю (по образцу Формы 1/112, приказ МЧС № 192)."""

    count: int
    within: int  # уложились в норматив
    within_share: float | None
    median_s: float | None
    p90_s: float | None
    avg_s: float | None
    norm_s: float | None  # норматив; если у занятий он разный — самый частый


def norm_stat(samples: list[tuple[float, float]]) -> NormStat:
    """`samples` — пары (факт, норматив) в секундах: у каждого занятия может быть свой норматив."""
    if not samples:
        return NormStat(0, 0, None, None, None, None, None)
    facts = [f for f, _ in samples]
    within = sum(1 for f, n in samples if f <= n)
    norms = [n for _, n in samples]
    return NormStat(
        count=len(samples),
        within=within,
        within_share=round(within / len(samples), 3),
        median_s=percentile(facts, 50),
        p90_s=percentile(facts, 90),
        avg_s=round(sum(facts) / len(facts), 1),
        norm_s=max(set(norms), key=norms.count),
    )


def error_key(criterion_title: str, text: str) -> str:
    """Ключ «типичной ошибки»: критерий и суть замечания без подробностей конкретной карточки — перечней после
    двоеточия, пояснений в скобках и чисел («номер дома не совпадает (эталон 37)» = «… (эталон 7)»)."""
    core = re.split(r"[;:(]| — ", text)[0]
    core = re.sub(r"\d+(?:[.,]\d+)?", "N", core).strip()
    return f"{criterion_title}: {core[:90]}"


def next_difficulty(difficulties: list[int], recent_scores: list[float], threshold: float = 70) -> tuple[int, str]:
    """Сложность следующего задания: текущий уровень — медиана сложности отработанных сценариев; при стабильно
    высоком балле — на ступень выше, при низком — ниже (ПС 12.002 C/05: тренинги по выявленным трудностям)."""
    level = sorted(difficulties)[len(difficulties) // 2] if difficulties else 2
    if len(recent_scores) < 3:
        return level, f"мало оценённых карточек ({len(recent_scores)}), оставлен уровень {level}"
    avg = sum(recent_scores) / len(recent_scores)
    if avg >= threshold + 15 and level < 5:
        return level + 1, f"средний балл последних карточек {avg:.0f} ≥ {threshold + 15:.0f} — сложность выше"
    if avg < threshold - 10 and level > 1:
        return level - 1, f"средний балл последних карточек {avg:.0f} < {threshold - 10:.0f} — сложность ниже"
    return level, f"средний балл последних карточек {avg:.0f} — уровень {level} сохранён"
