"""Неречевые звуки и волнение реплики заявителя для синтеза речи (F3).

Состояние уже есть: напряжение `CallerTone` (п. 3.6), уровень ECCS и звуки профиля (п. 3.7, `psy.voice_for`),
ремарки модели («плачет»). Здесь они сводятся к двум параметрам голоса — `sounds` и `agitation` (0–3); как их
передать модели, решает адаптер синтеза (`aiskra/ai/adapters/speech_markup.py`). Текст реплики не меняется.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from aiskra.modules.training.domain.psy import REMARK_SOUND

MAX_SOUNDS = 2
_LEVEL_AGITATION = {1: 0, 2: 1, 3: 2, 4: 3, 5: 3}  # уровень ECCS 1–5 → волнение голоса 0–3
_INTENSITY_SHIFT = {1: -1, 2: 0, 3: 1}  # интенсивность модификатора в занятии: сдержанно / обычно / ярко
_SMOKE = re.compile(r"\bдым|\bгарь|\bзадыха", re.IGNORECASE)  # говорит о дыме — подкашливает


def agitation(tension: int | None, level: int | None = None, intensity: int = 2) -> int:
    """Волнение голоса 0–3: по уровню ECCS, если у звонка профиль, иначе по напряжению 0–10."""
    if level is not None:
        base = _LEVEL_AGITATION.get(level, 0)
    else:
        t = tension or 0
        base = 3 if t >= 8 else 2 if t >= 6 else 1 if t >= 4 else 0
    return max(0, min(3, base + _INTENSITY_SHIFT.get(intensity, 0)))


def sounds(
    text: str,
    *,
    agitation: int,
    remarks: Sequence[str] = (),
    profile_voice: Mapping[str, Any] | None = None,
    breathing: str | None = None,
) -> tuple[str, ...]:
    """Звуки реплики, не больше двух: ремарки и звуки профиля, при волнении без них — дыхание по состоянию,
    и кашель, если заявитель говорит о дыме."""
    out: list[str] = []

    def add(s: str) -> None:
        if s and s != "hangup" and s not in out:
            out.append(s)

    for r in remarks:
        add(REMARK_SOUND.get(r.strip().lower(), ""))
    if profile_voice:
        for s in profile_voice.get("nonverbal") or []:
            add(str(s))
    if not out and agitation >= 2:
        add({"irregular": "gasp", "rapid": "pant"}.get(breathing or "", ""))
    if agitation >= 1 and _SMOKE.search(text):
        add("cough")
    return tuple(out[:MAX_SOUNDS])
