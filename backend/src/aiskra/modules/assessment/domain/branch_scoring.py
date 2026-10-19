"""Блок оценки «Развитие ситуации» (F5, ADR-0014): итог ветвящегося сценария.

Итог считает движок ветвления модуля training по фактам звонка и карточки; сюда приходит готовый разбор — итог, путь,
развилки, время ключевых решений. Балл блока — по коду итога. Вес в итоговом балле по умолчанию 0 (информативно):
преподаватель задаёт его в занятии, как вес блока «Работа с заявителем».
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Балл итога: благоприятный — полный, частичный — выше порога «зачтено» по умолчанию (70) не дотягивает, чтобы
# частичный исход не выглядел успехом; неблагоприятный и трагический — ниже.
OUTCOME_SCORE = {"favorable": 100.0, "partial": 60.0, "adverse": 30.0, "tragic": 0.0}


@dataclass(frozen=True)
class BranchAttempt:
    debrief: dict[str, Any]  # итог, путь, развилки (training/domain/branching.py:debrief)
    weight: float = 0.0
    final: bool = False  # итог окончательный: разговор завершён, карточка сохранена
    call_id: str = ""
    stats: dict[str, Any] = field(default_factory=dict)


def branch_details(a: BranchAttempt) -> dict[str, Any]:
    """Блок `details.branch`. Пока итога нет (разговор идёт), в итог балла блок не входит."""
    outcome = a.debrief.get("outcome") if a.final else None
    code = outcome.get("code") if outcome else None
    return {
        **a.debrief,
        "outcome": outcome,
        "final": bool(outcome),
        "score": OUTCOME_SCORE.get(code) if code else None,
        "passed": code in ("favorable", "partial") if code else None,
        "weight": a.weight if outcome else 0.0,
        "critical": [],
        "call_id": a.call_id,
    }


def outcome_counts(blocks: list[dict[str, Any]]) -> dict[str, int]:
    """Распределение итогов ситуаций по группе (RF5-08): сколько звонков каким исходом закончились."""
    counts = dict.fromkeys(OUTCOME_SCORE, 0)
    for b in blocks:
        code = (b.get("outcome") or {}).get("code")
        if code in counts:
            counts[code] += 1
    return counts
