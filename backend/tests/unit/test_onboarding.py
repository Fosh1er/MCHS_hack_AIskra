"""Прогресс обучения интерфейсу (п. 5.3): правила домена без БД."""

from __future__ import annotations

import pytest

from aiskra.modules.identity.domain.onboarding import MAX_TOURS, Onboarding, OnboardingAction
from aiskra.shared.errors import DomainError


def test_new_user_has_nothing_seen() -> None:
    state = Onboarding.from_json(None)
    assert state.dismissed is False and state.seen == []


def test_seen_is_recorded_once() -> None:
    state = Onboarding()
    state.apply(OnboardingAction.SEEN, "journal-112")
    state.apply(OnboardingAction.SEEN, "journal-112")
    state.apply(OnboardingAction.SEEN, "card-112")
    assert state.seen == ["journal-112", "card-112"]
    assert Onboarding.from_json(state.to_json()).seen == ["journal-112", "card-112"]


def test_dismiss_and_reset() -> None:
    state = Onboarding(seen=["welcome"])
    state.apply(OnboardingAction.DISMISS)
    assert state.dismissed is True and state.seen == ["welcome"]
    state.apply(OnboardingAction.RESET)
    assert state.dismissed is False and state.seen == []


@pytest.mark.parametrize("tour", [None, "", "Journal 112", "журнал", "x" * 41, "../etc"])
def test_bad_tour_id_rejected(tour: str | None) -> None:
    with pytest.raises(DomainError):
        Onboarding().apply(OnboardingAction.SEEN, tour)


def test_size_is_limited() -> None:
    state = Onboarding(seen=[f"t{i}" for i in range(MAX_TOURS)])
    with pytest.raises(DomainError):
        state.apply(OnboardingAction.SEEN, "one-more")


def test_several_tours_all_or_nothing() -> None:
    """П. 5.4: несколько экранов — одной записью; повтор не задваивается, ошибка в одном — не записан ни один."""
    state = Onboarding(seen=["teacher-home"])
    state.mark_seen(["teacher-welcome", "teacher-home", "teacher-welcome"])
    assert state.seen == ["teacher-home", "teacher-welcome"]
    with pytest.raises(DomainError):
        state.mark_seen(["teacher-report", "Плохой id"])
    assert "teacher-report" not in state.seen
    full = Onboarding(seen=[f"t{i}" for i in range(MAX_TOURS - 1)])
    with pytest.raises(DomainError):
        full.mark_seen(["a", "b"])  # не влезают оба — не записан ни один
    assert len(full.seen) == MAX_TOURS - 1


def test_corrupted_value_is_ignored() -> None:
    state = Onboarding.from_json({"dismissed": 1, "seen": ["ok-1", 5, "Bad Id", None]})
    assert state.dismissed is True and state.seen == ["ok-1"]
    assert Onboarding.from_json("мусор").seen == []
