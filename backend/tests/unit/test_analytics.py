"""Чистые функции аналитики преподавателя (specs/4.5): процентили, «норматив / факт», сложность задания."""

from aiskra.modules.assessment.domain.analytics import error_key, next_difficulty, norm_stat, percentile
from aiskra.modules.assessment.domain.scoring import CARD_NORM_SECONDS


def test_card_norm_is_pp1931() -> None:
    assert CARD_NORM_SECONDS == 75  # ПП РФ № 1931, п. 9 «р»: опрос до карточки ДДС — в среднем 75 с


def test_percentile_interpolates_like_excel() -> None:
    assert percentile([], 50) is None
    assert percentile([10], 90) == 10
    assert percentile([10, 20, 30, 40], 50) == 25
    assert percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 90) == 9.1


def test_norm_stat_uses_each_sessions_own_norm() -> None:
    s = norm_stat([(60, 75), (80, 75), (70, 90), (100, 90)])
    assert s.count == 4 and s.within == 2 and s.within_share == 0.5
    assert s.median_s == 75 and s.avg_s == 77.5 and s.norm_s in (75, 90)
    empty = norm_stat([])
    assert empty.count == 0 and empty.within_share is None and empty.norm_s is None


def test_error_key_drops_card_specifics() -> None:
    assert error_key("Адрес", "номер дома не совпадает (эталон 37)") == error_key(
        "Адрес", "номер дома не совпадает (эталон 7)"
    )
    assert error_key("Службы", "не направлено в: МОЭК, Мосгаз") == "Службы: не направлено в"
    assert error_key("Время", "заполнена за 78 с при нормативе 75 с") == "Время: заполнена за N с при нормативе N с"
    assert error_key("Адрес", "улица не совпадает — указано «Арбат»") == "Адрес: улица не совпадает"


def test_next_difficulty_follows_scores() -> None:
    assert next_difficulty([], [])[0] == 2
    assert next_difficulty([2, 3, 3], [90, 95])[0] == 3  # мало данных — уровень сохраняется
    assert next_difficulty([2, 3, 3], [90, 88, 95])[0] == 4
    assert next_difficulty([2, 2, 2], [40, 50, 55])[0] == 1
    assert next_difficulty([5, 5, 5], [99, 99, 99])[0] == 5
    level, reason = next_difficulty([3, 3, 3], [72, 75, 70])
    assert level == 3 and "сохранён" in reason
