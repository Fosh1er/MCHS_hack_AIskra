"""П. 1.3: статусы сохранённой карточки, ЧС/ЧП, «дополнение», отработки — правила домена."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from aiskra.modules.incidents.domain.card import Address, Applicant, ApplicantStatus, CardFlags, IncidentCardData
from aiskra.modules.incidents.domain.incident import Appendix, CardService, CardStatus, IncidentCard, Workout
from aiskra.shared.errors import DomainError

T0 = datetime(2026, 9, 27, 10, 0, tzinfo=UTC)


def saved_card() -> IncidentCard:
    card = IncidentCard(number=36900001, author_id=uuid4(), opened_at=T0)
    data = IncidentCardData(
        card_types=["101"],
        incident_types=["1050001"],
        applicant=Applicant(name="Иванов Иван", status=ApplicantStatus.WITNESS),
        address=Address(street="Новая Басманная улица", house="6"),
        description="Горит квартира",
    )
    card.save(data, [CardService(code="S101", is_main=True)], T0)
    return card


def test_status_flow_worked_checked_returned() -> None:
    card, teacher = saved_card(), uuid4()
    with pytest.raises(DomainError):
        card.mark_checked(teacher, T0)  # сначала «отработана»
    card.mark_worked(T0)
    assert card.status is CardStatus.WORKED and card.worked_at == T0
    with pytest.raises(DomainError):
        card.mark_worked(T0)
    card.mark_checked(teacher, T0)
    assert card.status is CardStatus.CHECKED and card.checked_by == teacher
    card.return_for_rework()
    assert card.status is CardStatus.REGISTERED and card.worked_at is None and card.checked_by is None


def test_draft_and_empty_cards_are_not_changed() -> None:
    draft = IncidentCard(number=1, author_id=uuid4(), opened_at=T0)
    with pytest.raises(DomainError) as exc:
        draft.set_flags(emergency=True, incident=False)
    assert exc.value.code == "card_not_saved"
    empty = IncidentCard(number=2, author_id=uuid4(), opened_at=T0)
    empty.save(IncidentCardData(flags=CardFlags(no_contact=True)), [], T0)
    with pytest.raises(DomainError) as exc:
        empty.append(Appendix(description_add="x"))
    assert exc.value.code == "card_completed"


def test_flags_report_changes() -> None:
    card = saved_card()
    assert card.set_flags(emergency=True, incident=False) == ["ЧС"]
    assert card.set_flags(emergency=True, incident=True) == ["ЧП"]
    assert card.data.flags.emergency and card.data.flags.incident
    assert card.set_flags(emergency=True, incident=True) == []


def test_append_only_empty_fields_description_and_victims() -> None:
    card = saved_card()
    changed = card.append(
        Appendix(
            fields={"address.flat": "12", "phones.on_site": ""}, description_add="Дым на лестнице", victims_count=2
        )
    )
    assert changed == ["квартира/офис", "описание", "пострадавшие"]
    assert card.data.address.flat == "12" and card.data.description == "Горит квартира\nДым на лестнице"
    assert card.data.victims.has and card.data.victims.count == 2
    with pytest.raises(DomainError) as exc:
        card.append(Appendix(fields={"address.flat": "13"}))
    assert exc.value.code == "field_not_empty"
    with pytest.raises(DomainError) as exc:
        card.append(Appendix(fields={"applicant.status": "victim"}))
    assert exc.value.code == "field_not_appendable"


def test_checked_card_is_not_appended() -> None:
    card = saved_card()
    card.mark_worked(T0)
    card.mark_checked(uuid4(), T0)
    with pytest.raises(DomainError) as exc:
        card.append(Appendix(description_add="ещё"))
    assert exc.value.code == "card_checked"


def test_workout_needs_target_and_message() -> None:
    Workout(card_id=uuid4(), author_id=uuid4(), at=T0, service_code="DEP_GKH", message="передано дежурному")
    Workout(card_id=uuid4(), author_id=uuid4(), at=T0, target="заявитель", message="уточнили этаж")
    for kw in [{"message": "x"}, {"service_code": "S101", "message": "  "}]:
        with pytest.raises(DomainError):
            Workout(card_id=uuid4(), author_id=uuid4(), at=T0, **kw)  # type: ignore[arg-type]
