"""Повторные обращения и связи карточек (п. 1.6, ТЗ 4.6) — чистые правила.

Совпадение — по любому из трёх телефонов (АОН, предоставленный, на место) или по адресу (улица и дом). Связь —
одноуровневая: подчинённая карточка указывает на главную; у главной главной нет («сделать главной» — `image67`)."""

from __future__ import annotations

import re
from uuid import UUID

from aiskra.shared.errors import DomainError


def phone_key(phone: str | None) -> str:
    """Последние 10 цифр: «+7 (916) 123-45-67» и «89161234567» — один номер. Короче 6 цифр — не телефон."""
    digits = re.sub(r"\D", "", phone or "")
    return digits[-10:] if len(digits) >= 6 else ""


def address_key(street: str | None, house: str | None) -> str:
    s = re.sub(r"[^а-яa-z0-9]+", " ", (street or "").lower().replace("ё", "е")).strip()
    h = re.sub(r"\s+", "", (house or "").lower())
    return f"{s}|{h}" if s and h else ""


def link_target(card_id: UUID, main_id: UUID, main_of_main: UUID | None) -> UUID:
    """К какой карточке привязать: к главной самой выбранной (связь одноуровневая); к себе — нельзя."""
    target = main_of_main or main_id
    if target == card_id:
        raise DomainError("Карточку нельзя привязать к самой себе", code="link_self")
    return target
