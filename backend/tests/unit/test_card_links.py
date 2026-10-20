"""П. 1.6 (ТЗ 4.6): правила совпадения номеров и адресов, одноуровневая связь карточек."""

from uuid import uuid4

import pytest

from aiskra.modules.incidents.domain.links import address_key, link_target, phone_key
from aiskra.shared.errors import DomainError


def test_phone_and_address_keys() -> None:
    assert phone_key("+7 (917) 980-54-13") == phone_key("89179805413") == "9179805413"
    assert phone_key("112") == "" and phone_key(None) == ""
    assert address_key("Новая Басманная улица", "6") == address_key("новая басманная  улица", " 6 ")
    assert address_key("Тверская", "") == ""


def test_link_goes_to_root_and_not_to_itself() -> None:
    card, main, root = uuid4(), uuid4(), uuid4()
    assert link_target(card, main, None) == main
    assert link_target(card, main, root) == root  # привязка к подчинённой — к её главной
    with pytest.raises(DomainError):
        link_target(card, card, None)
    with pytest.raises(DomainError):
        link_target(card, main, card)
