"""Шкала готовности к допуску (specs/4.6): Программа подготовки ЕДДС 2023 — балл и соблюдение срока."""

from aiskra.modules.assessment.domain.readiness import assess_readiness, timing_class

ON_TIME = [(60.0, 75.0)] * 10


def test_scale_by_score_when_on_time() -> None:
    assert assess_readiness([95] * 6, ON_TIME).grade_label == "отлично"
    assert assess_readiness([80] * 6, ON_TIME).grade_label == "хорошо"
    assert assess_readiness([65] * 6, ON_TIME).grade_label == "удовлетворительно"
    low = assess_readiness([50] * 6, ON_TIME)
    assert low.grade == 2 and not low.ready and low.status == "нужна дополнительная практика"
    assert "ниже 60" in low.reasons[-1]


def test_time_overrun_lowers_grade() -> None:
    slight = [(60.0, 75.0)] * 7 + [(100.0, 75.0)] * 3  # 70 % в нормативе, 90-й процентиль ≈ 1,33 норматива
    assert timing_class(slight)[0] == "небольшое превышение"
    r = assess_readiness([95] * 10, slight)
    assert r.grade == 3 and r.ready and "превышением времени" in r.reasons[-1]
    heavy = [(200.0, 75.0)] * 10
    assert timing_class(heavy)[0] == "значительное превышение"
    assert assess_readiness([95] * 10, heavy).grade == 2


def test_not_enough_cards_and_missing_time() -> None:
    r = assess_readiness([95, 95], ON_TIME)
    assert r.grade is None and not r.ready and r.grade_label == "недостаточно данных"
    assert r.status == "нужно ещё 3 оценённые карточки"
    assert assess_readiness([95] * 4, ON_TIME).status == "нужна ещё 1 оценённая карточка"
    assert assess_readiness([95], ON_TIME, min_cards=6).status == "нужно ещё 5 оценённых карточек"
    assert assess_readiness([92] * 5, []).grade == 5  # времени нет (ДДС без решения) — по баллу
