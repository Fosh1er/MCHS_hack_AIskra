"""Статусы службы в АРМ ДДС (п. 2.2): переходы по списку оригинала и обязательные поля."""

from itertools import pairwise

import pytest

from aiskra.modules.incidents.domain.dds import (
    FINAL,
    ServiceStatus,
    call_sign,
    check_brigades,
    check_transition,
    next_statuses,
)
from aiskra.shared.errors import DomainError

S = ServiceStatus


def test_first_choice_is_accepted_or_rejected() -> None:
    assert next_statuses(S.ADDED) == next_statuses(S.RECEIVED) == [S.ACCEPTED, S.REJECTED]


def test_chain_to_works_completed() -> None:
    chain = [S.RECEIVED, S.ACCEPTED, S.RESPONSE_STARTED, S.ARRIVED, S.WORKS_IN_PROGRESS, S.WORKS_COMPLETED]
    for cur, new in pairwise(chain):
        check_transition(cur, new, "23", "комментарий")


def test_refusal_from_any_step_after_accept() -> None:
    for cur in (S.ACCEPTED, S.RESPONSE_STARTED, S.ARRIVED, S.WORKS_IN_PROGRESS):
        assert S.WORKS_REFUSED in next_statuses(cur)


def test_final_statuses_have_no_next() -> None:
    for st in FINAL:
        assert next_statuses(st) == []
        with pytest.raises(DomainError):
            check_transition(st, S.ACCEPTED, "1", "x")


def test_skip_and_required_fields() -> None:
    with pytest.raises(DomainError, match="нельзя перейти"):
        check_transition(S.RECEIVED, S.ARRIVED, "", "")
    with pytest.raises(DomainError, match="номер наряда"):
        check_transition(S.RECEIVED, S.ACCEPTED, "", "отправлен экипаж")
    with pytest.raises(DomainError, match="комментарий"):
        check_transition(S.RECEIVED, S.REJECTED, "", " ")
    check_transition(S.ACCEPTED, S.RESPONSE_STARTED, "", "")  # промежуточные статусы — без обязательных полей


def test_brigades_only_own_free_and_not_on_reject() -> None:
    """П. 5.5: силы — только из справочника своей службы, не занятые на другой карточке, не при «Не принята»."""
    known = {"S103:Л-101", "S103:Р-21"}
    check_brigades("S103", S.ACCEPTED, ["S103:Л-101"], known, {})
    check_brigades("S103", S.REJECTED, [], known, {})
    cases = [
        (S.ACCEPTED, ["S101:АЦ-11"], {}, "unknown_brigade"),
        (S.ACCEPTED, ["S103:Р-21"], {"S103:Р-21": 17}, "brigade_busy"),
        (S.ACCEPTED, ["S103:Л-101", "S103:Л-101"], {}, "bad_brigades"),
        (S.REJECTED, ["S103:Л-101"], {}, "brigades_on_reject"),
    ]
    for status, chosen, busy, code in cases:
        with pytest.raises(DomainError) as e:
            check_brigades("S103", status, chosen, known, busy)
        assert e.value.code == code
    assert call_sign("S103:Р-21") == "Р-21"
