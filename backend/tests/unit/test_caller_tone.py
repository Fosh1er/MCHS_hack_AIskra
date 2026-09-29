"""Состояние ИИ-заявителя (п. 3.6, V1): начальное состояние, правила реакции на реплики оператора, защита от
«накрутки», хранение и окраска офлайн-ответа."""

from aiskra.modules.training.domain.tone import (
    CallerTone,
    Emotion,
    ToneSnapshot,
    color_reply,
    incident_group,
    initial_tone,
    speech_speed,
    speech_style,
    tone_for_legend,
)


def panic() -> CallerTone:
    return initial_tone(5, 1)  # пожар, сложность 5


def test_initial_tone_by_difficulty_and_group() -> None:
    t = panic()
    assert (t.tension, t.trust, t.readiness, t.emotion) == (9, 3, 4, Emotion.PANIC)
    assert initial_tone(3, 1).emotion is Emotion.FEAR  # паника ниже пика — страх
    assert initial_tone(4, 2).emotion is Emotion.SHOCK  # ДТП
    assert initial_tone(4, 14).emotion is Emotion.IRRITATION  # городское хозяйство
    assert initial_tone(4, 22).emotion is Emotion.FEAR  # медицинская помощь — по умолчанию страх
    assert initial_tone(None, None).emotion is Emotion.CALM  # карточка без сценария


def test_incident_group_from_classifier_code() -> None:
    assert incident_group("1010101") == 1
    assert incident_group("15260000") == 15
    assert incident_group("101") is None and incident_group(None) is None and incident_group("abc0000000") is None


def test_legend_sets_difficulty_and_whisper() -> None:
    legend = {"difficulty": 4, "facts": {"offense": "похоже на правонарушение"}}
    t = tone_for_legend(legend, "15010100")
    assert t.tension == 8 and t.whisper and t.delivery()[1] == "whisper"
    assert not tone_for_legend(legend, "1010101").whisper  # шёпот — только нарушение правопорядка
    assert tone_for_legend({}, None).tension == 2


def test_invalidating_and_pressure_raise_tension() -> None:
    t = panic()
    changes = t.react("Успокойтесь! Быстрее говорите!", topic=None, revealed=[])
    assert [c.reason for c in changes] == ["invalidating", "pressure"]
    assert (t.tension, t.trust, t.readiness) == (10, 0, 1)  # напряжение упёрлось в предел шкалы


def test_calming_takes_three_replicas() -> None:
    t = panic()
    seen = []
    for phrase in ("Я вас слышу.", "Помощь уже едет.", "Оставайтесь на линии."):
        t.react(phrase, topic=None, revealed=[])
        seen.append(t.tension)
    assert seen == [7, 5, 3] and t.emotion is Emotion.RELIEF


def test_category_once_per_replica() -> None:
    t = panic()
    changes = t.react("Я вас слышу, помощь уже едет, оставайтесь на линии", topic=None, revealed=[])
    assert [(c.reason, c.fragment, c.tension) for c in changes] == [("calming", "я вас слышу", -2)]
    assert t.tension == 7


def test_same_phrase_counts_once() -> None:
    t = panic()
    t.react("Я вас слышу", topic=None, revealed=[])
    assert t.react("Я вас слышу", topic=None, revealed=[]) == [] and t.tension == 7


def test_calming_is_capped() -> None:
    t = panic()
    for phrase in ("я вас слышу", "помощь уже едет", "оставайтесь на линии", "вы в безопасности"):
        t.react(phrase, topic=None, revealed=[])
    assert t.tension == 3 and t.calmed == 6  # четвёртая фраза напряжение уже не снижает
    assert t.trust == 10  # доверие растёт дальше


def test_repeated_invalidating_keeps_annoying() -> None:
    t = initial_tone(2, 1)
    t.react("Успокойтесь", topic=None, revealed=[])
    t.react("Успокойтесь", topic=None, revealed=[])
    assert t.tension == 8  # повторное «успокойтесь» злит снова, в отличие от успокаивающих фраз


def test_short_question_and_confirmation_not_penalized() -> None:
    t = panic()
    changes = t.react("Адрес?", topic="address", revealed=["opening"])
    assert [(c.reason, c.readiness) for c in changes] == [("on_topic", 1)] and t.tension == 9
    # подтверждение уже названного адреса — норма опроса 112, не штраф
    assert t.react("Повторите адрес", topic="address", revealed=["opening", "address"]) == []


def test_round_trip_and_broken_json() -> None:
    t = panic()
    t.react("Я вас слышу", topic=None, revealed=[])
    back = CallerTone.from_json(t.to_json())
    assert back == t
    assert CallerTone.from_json({"base": "nope"}) is None and CallerTone.from_json(None) is None


def test_snapshot_has_no_legend_and_round_trips() -> None:
    t = panic()
    snap = t.snapshot(t.react("Успокойтесь", topic=None, revealed=[]))
    data = snap.to_json()
    assert set(data) == {
        "emotion",
        "emotion_title",
        "tension",
        "trust",
        "readiness",
        "band",
        "pace",
        "volume",
        "breathing",
        "changes",
    }
    assert data["emotion_title"] == "паника" and data["pace"] == "very_fast"
    assert data["changes"][0]["fragment"] == "успокойтесь"
    assert ToneSnapshot.from_json(data) == snap and ToneSnapshot.from_json({"emotion": "x"}) is None


def test_color_reply_keeps_facts() -> None:
    fact = "Тверская улица, 7"
    assert fact in color_reply(fact, panic(), 0) and color_reply(fact, panic(), 0) != fact
    assert color_reply("Помогите, скорее!", panic(), 0) == "Помогите, скорее!"  # и так торопит
    assert color_reply(fact, initial_tone(3, 1), 0).endswith(fact)
    calm = initial_tone(1, 1)
    assert color_reply(fact, calm, 0) == fact
    relieved = panic()
    for phrase in ("я вас слышу", "помощь уже едет", "оставайтесь на линии"):
        relieved.react(phrase, topic=None, revealed=[])
    assert color_reply(fact, relieved, 0) == f"Да, хорошо. {fact}"


def test_speech_style_and_speed_follow_tone() -> None:
    """П. 3.6, V2: подача для серверного синтеза — словами (стиль) и темпом."""
    t = panic()
    style = speech_style(t.snapshot())
    assert style.startswith("a panicking caller") and "very fast" in style and "gasping" in style
    assert speech_speed(t.snapshot()) == 1.3
    whisper = tone_for_legend({"difficulty": 4, "facts": {"offense": "x"}}, "15010100").snapshot()
    assert "whispering" in speech_style(whisper) and "a frightened caller" in speech_style(whisper)
    assert speech_speed(initial_tone(1, 1).snapshot()) == 0.9
