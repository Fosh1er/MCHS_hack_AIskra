def test_custom_answer_and_fact_check() -> None:
    """ТЗ 3.4: переписанный ответ звучит в звонке; факты легенды (адрес, имя, пострадавшие) менять нельзя."""
    from aiskra.modules.training.domain.actors import answer_fact_errors, applicant_reply

    legend = {
        "address": {"label": "Новая Басманная улица, 5", "street": "Новая Басманная улица", "house": "5"},
        "applicant": {"name": "Петрова Анна", "status": "witness"},
        "victims": {"has": True, "count": 2},
        "answers": {"address": "Ой, Новая Басманная, дом 5, скорее!"},
    }
    assert applicant_reply(legend, "Назовите адрес", []).text == "Ой, Новая Басманная, дом 5, скорее!"
    assert applicant_reply(legend, "Кем вы приходитесь пострадавшему?", []).topic == "status"
    assert answer_fact_errors(legend, "address", "Басманная, дом 5") == []
    assert answer_fact_errors(legend, "address", "Тверская, дом 7")  # улица и дом — не из легенды
    assert answer_fact_errors(legend, "name", "Я Петрова") == []
    assert answer_fact_errors(legend, "name", "Иванова я")
    assert answer_fact_errors(legend, "victims", "Нет, никто не пострадал")
    assert answer_fact_errors(legend, "victims", "Двое лежат, помогите") == []
