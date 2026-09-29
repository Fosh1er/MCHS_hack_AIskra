"""Проверка грамотности после ручной правки сценария (п. 3.6): детерминированные правила."""

from aiskra.modules.training.domain.spelling import check_legend, check_text


def rules(field: str, text: str) -> set[str]:
    return {r.rule for r in check_text(field, text)}


def test_clean_text_has_no_remarks() -> None:
    assert check_text("what", "Горит балкон на третьем этаже, идёт сильный дым.") == []
    assert check_text("title", "Пожар на балконе") == []  # у названия точка в конце не нужна


def test_typical_mistakes_are_found() -> None:
    assert "повтор слова" in rules("what", "Горит горит балкон.")
    lat = check_text("what", "Пожар в Mоскве.")  # латинская M
    assert lat[0].rule == "латинская буква в русском слове" and lat[0].fix == "Москве"
    assert "пробел перед знаком препинания" in rules("what", "Горит балкон , дым.")
    assert "строчная буква в начале предложения" in rules("what", "Горит балкон. дым идёт.")
    assert "нет знака препинания в конце" in rules("opening", "Алло, у нас пожар")
    assert "незакрытые кавычки или скобки" in rules("details", "Дом (жилой, пятиэтажный.")


def test_check_legend_marks_fields() -> None:
    remarks = check_legend({"title": "Пожар", "opening": "алло, горит", "what": "", "details": ""})
    assert {r.field for r in remarks} == {"opening"}
