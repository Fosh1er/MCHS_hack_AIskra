"""Карточка 112 как сущность: обязательные поля, пустая карточка, повторное сохранение, таймер."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from aiskra.modules.incidents.domain.card import Address, Applicant, ApplicantStatus, CardFlags, IncidentCardData
from aiskra.modules.incidents.domain.incident import CardService, CardStatus, IncidentCard, missing_for_save
from aiskra.shared.errors import DomainError

T0 = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
S101 = [CardService(code="S101", is_main=True)]


def full_card() -> IncidentCardData:
    return IncidentCardData(
        card_types=["101"],
        incident_types=["1050001"],
        applicant=Applicant(name="Иванов Иван", status=ApplicantStatus.WITNESS),
        address=Address(street="Новая Басманная улица", house="6", district="basmannyy", okrug="CAO"),
        description="Горит квартира на 3 этаже, дым из окна",
    )


def new_card() -> IncidentCard:
    return IncidentCard(number=36900001, author_id=uuid4(), opened_at=T0)


def test_minimum_for_save_like_instruction() -> None:
    assert missing_for_save(IncidentCardData(), []) == ["Что случилось"]
    empty_reaction = IncidentCardData(card_types=["101"], incident_types=["1050001"])
    assert missing_for_save(empty_reaction, []) == [
        "Адрес (дом, описательный адрес или координаты)",
        "Фамилия и имя заявителя",
        "Статус заявителя",
        "Описание со слов заявителя",
        "Службы",
    ]
    assert missing_for_save(full_card(), S101) == []


def test_service_type_needs_no_address() -> None:
    """Служебные типы (Консультация, Справка…) не дают конечного типа классификатора."""
    assert missing_for_save(IncidentCardData(card_types=["consultation"]), []) == []


def test_address_alternatives() -> None:
    data = full_card()
    data.address = Address(descriptive="у входа в парк «Сокольники»")
    assert missing_for_save(data, S101) == []
    data.address = Address(lat=55.77, lon=37.66)
    assert missing_for_save(data, S101) == []


def test_save_registers_card_and_counts_processing_time() -> None:
    card = new_card()
    card.save(full_card(), S101, T0 + timedelta(seconds=74, milliseconds=500))
    assert card.status is CardStatus.REGISTERED and card.processing_ms == 74_500
    assert card.data.services == ["S101"]
    with pytest.raises(DomainError) as exc:
        card.save(full_card(), S101, T0 + timedelta(minutes=2))
    assert exc.value.code == "card_already_saved"


def test_incomplete_card_is_rejected_with_field_list() -> None:
    with pytest.raises(DomainError) as exc:
        new_card().save(IncidentCardData(card_types=["101"], incident_types=["1050001"]), [], T0)
    assert exc.value.code == "card_incomplete" and "Статус заявителя" in exc.value.message


def test_empty_call_is_completed_without_services() -> None:
    card = new_card()
    card.save(IncidentCardData(flags=CardFlags(no_contact=True)), S101, T0 + timedelta(seconds=5))
    assert card.status is CardStatus.COMPLETED and card.services == []


def test_duplicate_service_is_rejected() -> None:
    with pytest.raises(DomainError):
        new_card().save(full_card(), [*S101, CardService(code="S101")], T0)
