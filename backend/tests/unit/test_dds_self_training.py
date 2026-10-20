"""Правила выбора учебной карточки самостоятельной тренировки ДДС (п. 2.1, рекомендация экспертов п. 10)."""

import random
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from aiskra.modules.training.domain.self_training import pick_for_service, reference_services, self_training_rng

A, B, C = (UUID(int=i) for i in (1, 2, 3))


def ref(*codes: str) -> dict[str, object]:
    return {"services": [{"code": c, "main": i == 0} for i, c in enumerate(codes)]}


BANK = [(A, ref("S101", "DDS_BASMANNYY")), (B, ref("S103")), (C, ref("S101"))]


def test_reference_services_ignores_broken_rows() -> None:
    assert reference_services({"services": [{"code": "S101"}, {"main": True}, "x"]}) == {"S101"}
    assert reference_services({}) == set()


def test_only_scenarios_with_service_in_reference() -> None:
    picks = {pick_for_service(BANK, "S101", random.Random(i)) for i in range(50)}
    assert picks == {A, C}
    assert pick_for_service(BANK, "S103", random.Random(0)) == B
    assert pick_for_service(BANK, "S104", random.Random(0)) is None  # нет в банке — генерация на лету


def test_recent_scenarios_not_repeated_while_others_exist() -> None:
    assert {pick_for_service(BANK, "S101", random.Random(i), recent=[A]) for i in range(20)} == {C}
    assert pick_for_service(BANK, "S103", random.Random(0), recent=[B]) == B  # другого нет — повтор


def test_different_trainees_get_different_streams() -> None:
    now = datetime(2026, 10, 20, 21, 0, tzinfo=UTC)
    u1, u2 = uuid4(), uuid4()
    assert self_training_rng(u1, now).random() != self_training_rng(u2, now).random()
    assert self_training_rng(u1, now).random() != self_training_rng(u1, now + timedelta(seconds=1)).random()
    assert self_training_rng(u1, now, seed=7).random() == random.Random(7).random()  # тесты — своё зерно
    # выбор зависит от порядка банка только через сортировку — один и тот же rng даёт один и тот же сценарий
    assert pick_for_service(BANK, "S101", random.Random(3)) == pick_for_service(BANK[::-1], "S101", random.Random(3))
