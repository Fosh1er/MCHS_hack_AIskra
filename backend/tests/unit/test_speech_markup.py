"""F3: разметка текста для синтеза — звуки и волнение заявителя, факты реплики не меняются."""

from aiskra.ai.adapters.speech_markup import agitate, gemini_markup


def test_gemini_tags_first_sound_at_start_second_before_next_phrase() -> None:
    assert gemini_markup("Алло! У нас пожар.", ("sob", "cough")) == "<sob> Алло! <cough> У нас пожар."
    assert gemini_markup("Алло!", ("gasp", "sigh")) == "<gasp> Алло! <sigh>"


def test_gemini_ignores_unknown_and_duplicate_sounds_and_caps_at_two() -> None:
    assert gemini_markup("Да.", ("hangup", "sob", "sob")) == "<sob> Да."
    assert gemini_markup("А. Б. В.", ("sob", "gasp", "pant")) == "<sob> А. <gasp> Б. В."


def test_gemini_strong_agitation_breath_and_emphasis() -> None:
    out = gemini_markup("Скорее, пожалуйста. Он не дышит.", (), agitation=3)
    assert out == "СКОРЕЕ, пожалуйста. <heavy breath> Он не дышит."
    # звук дыхания уже есть — второго не добавляем
    assert "<heavy breath>" not in gemini_markup("Скорее. Он не дышит.", ("sob",), agitation=3)
    assert gemini_markup("Скорее. Он не дышит.", (), agitation=2) == "Скорее. Он не дышит."


def test_agitate_keeps_text_when_calm() -> None:
    text = "Улица Ленина, дом 5. Квартира 12."
    assert agitate(text, 0) == text and agitate(text, 1) == text


def test_agitate_exclaims_but_keeps_abbreviations_and_numbers() -> None:
    assert agitate("Вишнёвая ул. 7, кв. 12. Приезжайте скорее.", 2) == "Вишнёвая ул. 7, кв. 12. Приезжайте скорее!"
    assert agitate("Алло. Что мне делать?", 3) == "Алло! Алло! Что мне делать?!"
    assert agitate("Да, дом семь. Подъезд второй.", 2) == "Да, дом семь! Подъезд второй!"


def test_agitate_repeats_only_interjections() -> None:
    assert agitate("Пожар на кухне.", 3) == "Пожар на кухне!"
    assert agitate("помогите, тут дым.", 3) == "Помогите! помогите, тут дым!"
