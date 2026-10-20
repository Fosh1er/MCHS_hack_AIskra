"""Самостоятельная тренировка ДДС (п. 2.1, рекомендация экспертов п. 10): правила выбора учебной карточки.

Обучающийся вне занятия просит карточку для своей службы — система сама берёт утверждённый сценарий банка, где эта
служба есть в эталоне служб (иначе генерирует новый), выдаёт её только ему и сразу оценивает решение. Разным
обучающимся — разные карточки: выбор случайный, зерно — от пользователя и времени запроса."""

from __future__ import annotations

import hashlib
import random
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

MAX_SELF_WAITING = 3  # ожидающих решения учебных карточек у одного обучающегося
GENERATE_ATTEMPTS = 5  # сколько раз генератор пробует сценарий, где служба есть в эталоне


def self_training_rng(user_id: UUID, now: datetime, seed: int | None = None) -> random.Random:
    """Зерно — от пользователя и момента запроса: два обучающихся в одну секунду получают разные карточки."""
    if seed is not None:
        return random.Random(seed)
    digest = hashlib.sha256(f"{user_id}:{now.isoformat()}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def reference_services(reference_card: Mapping[str, Any]) -> set[str]:
    """Коды служб эталона карточки 112 сценария."""
    return {str(x["code"]) for x in reference_card.get("services") or [] if isinstance(x, Mapping) and x.get("code")}


def pick_for_service(
    candidates: Iterable[tuple[UUID, Mapping[str, Any]]],
    service_code: str,
    rng: random.Random,
    recent: Iterable[UUID] = (),
) -> UUID | None:
    """Случайный сценарий, в эталоне которого есть служба. Недавно выданные этому обучающемуся (`recent`) — только
    если других нет: подряд одна и та же ситуация не повторяется."""
    pool = sorted(sid for sid, ref in candidates if service_code in reference_services(ref))
    if not pool:
        return None
    seen = set(recent)
    fresh = [sid for sid in pool if sid not in seen]
    return rng.choice(fresh or pool)
