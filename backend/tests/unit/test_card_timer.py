"""П. 5.3: пауза таймера черновика карточки на время подсказок — не входит во время заполнения."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from aiskra.modules.incidents.domain.card import Address, Applicant, ApplicantStatus, IncidentCardData
from aiskra.modules.incidents.domain.incident import MAX_TIMER_PAUSE, CardService, IncidentCard
from aiskra.shared.errors import DomainError

T0 = datetime(2026, 9, 28, 10, 0, tzinfo=UTC)
DATA = IncidentCardData(
    card_types=["101"],
    incident_types=["1050001"],
    applicant=Applicant(name="Иванов Иван", status=ApplicantStatus.WITNESS),
    address=Address(street="Новая Басманная улица", house="6"),
    description="Горит квартира",
)
SERVICES = [CardService(code="S101", is_main=True)]


def draft() -> IncidentCard:
    return IncidentCard(number=36900001, author_id=uuid4(), opened_at=T0)


def at(seconds: int) -> datetime:
    return T0 + timedelta(seconds=seconds)


def test_pause_is_not_counted() -> None:
    card = draft()
    card.pause_timer(at(1))
    assert card.resume_timer(at(91)) == 90_000  # 90 с подсказок
    card.save(DATA, SERVICES, at(150))
    assert card.processing_ms == 60_000  # 150 с на часах − 90 с паузы


def test_without_pause_time_is_unchanged() -> None:
    card = draft()
    card.save(DATA, SERVICES, at(70))
    assert card.processing_ms == 70_000 and card.paused_ms is None


def test_one_pause_per_card() -> None:
    card = draft()
    card.pause_timer(at(0))
    card.pause_timer(at(5))  # повтор запроса — не ошибка, пауза та же
    card.resume_timer(at(30))
    assert card.resume_timer(at(40)) == 30_000  # повтор «запустить» ничего не меняет
    with pytest.raises(DomainError) as e:
        card.pause_timer(at(50))
    assert e.value.code == "timer_pause_used"


def test_pause_is_capped() -> None:
    card = draft()
    card.pause_timer(at(0))
    assert card.resume_timer(at(3600)) == int(MAX_TIMER_PAUSE.total_seconds() * 1000)


def test_saving_during_pause_ends_it() -> None:
    card = draft()
    card.pause_timer(at(10))
    card.save(DATA, SERVICES, at(40))
    assert card.pause_started_at is None and card.processing_ms == 10_000


def test_saved_card_cannot_be_paused() -> None:
    card = draft()
    card.save(DATA, SERVICES, at(40))
    with pytest.raises(DomainError):
        card.pause_timer(at(50))
