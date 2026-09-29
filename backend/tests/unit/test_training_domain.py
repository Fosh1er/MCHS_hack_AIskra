"""Сценарии и ролевые агенты (п. 3.2, 3.3): сборка эталона, офлайн-легенда, ответы заявителя и старшего группы."""

import random

from aiskra.modules.training.domain.actors import applicant_reply, brigade_reply, topic_of
from aiskra.modules.training.domain.scenario import (
    AddressFacts,
    IncidentFacts,
    ServiceFacts,
    build_scenario,
    humanize,
    legend_voice,
    offline_story,
)

FIRE = IncidentFacts(
    code="1010101",
    group_id=1,
    group_title="Пожары и задымления",
    card_type="101",
    card_type_title="101",
    sign1="на улице",
    sign2="мусор",
    sign3="открытое пламя",
    final_type="пожар: мусор",
    flags=["victims", "no_access"],
)
ADDR = AddressFacts(
    street="Новая Басманная улица",
    house="13",
    building="",
    structure="2",
    district="basmannyy",
    district_name="Басманный",
    okrug="CAO",
    lat=55.77,
    lon=37.65,
)
SERVICES = [ServiceFacts(code="S101", short="Служба 101", main=True, phone="+7 (495) 000-00-01")]


def scenario(flags: list[str]):  # type: ignore[no-untyped-def]
    story = offline_story(FIRE, ADDR, flags, 2)
    return build_scenario(
        incident=FIRE,
        address=ADDR,
        services=SERVICES,
        story=story,
        flags=flags,
        difficulty=2,
        rng=random.Random(1),
        source="template",
        author_id=None,
    )


def test_humanize_and_story() -> None:
    assert humanize(FIRE) == "горит мусор (на улице)"
    story = offline_story(FIRE, ADDR, ["victims"], 1)
    assert "Новая Басманная улица, 13 с2" in story["opening"] and "пострадавшие" in story["description"]


def test_reference_card_matches_legend() -> None:
    s = scenario(["victims"])
    ref, legend = s.reference_card, s.legend
    assert ref["card_types"] == ["101"] and ref["incident_types"] == ["1010101"]
    assert ref["questionnaire"]["101"] == {"Признак 1": "на улице", "Признак 2": "мусор", "Признак 3": "открытое пламя"}
    assert ref["card_flags"] == ["victims"] and legend["victims"]["has"] and ref["victims"] == legend["victims"]
    assert (
        ref["applicant"]["name"] == legend["applicant"]["name"] and ref["phones"]["aon"] == legend["applicant"]["phone"]
    )
    assert ref["address"]["district"] == "basmannyy" and ref["services"][0]["main"]
    assert s.reference_dds["first_status"] == "accepted" and s.reference_dds["main_service"] == "S101"


def test_applicant_answers_only_what_asked() -> None:
    legend = scenario(["victims"]).legend
    r = applicant_reply(legend, "Назовите адрес", [])
    assert "Новая Басманная" in r.text and r.revealed == ["address"]
    assert "пострадавшие есть" in applicant_reply(legend, "Есть пострадавшие?", r.revealed).text.lower()
    assert applicant_reply(legend, "Как вас зовут?", []).text == legend["applicant"]["name"]
    assert "Повторите" in applicant_reply(legend, "Какая погода?", []).text
    assert topic_of("Какой этаж?") == "floor"


def test_applicant_never_leaks_reference() -> None:
    legend = scenario([]).legend
    answers = " ".join(applicant_reply(legend, q, []).text for q in ("что случилось", "адрес", "кто вы", "телефон"))
    assert "1010101" not in answers and "Служба 101" not in answers


def test_brigade_reports_by_status() -> None:
    assert "Выезжаем" in brigade_reply({"service_status": "accepted", "order_no": "23"}, "Алло")
    assert "наряд 23" in brigade_reply({"service_status": "accepted", "order_no": "23"}, "Алло")
    assert "Прибыли" in brigade_reply({"service_status": "arrived"}, "Как обстановка?")


def test_legend_has_voice() -> None:
    """П. 3.6: генератор сам задаёт голос синтетического заявителя вместе с именем — для озвучки."""
    voices = set()
    for seed in range(20):
        s = build_scenario(
            incident=FIRE,
            address=ADDR,
            services=SERVICES,
            story={},
            flags=[],
            difficulty=2,
            rng=random.Random(seed),
            source="template",
            author_id=None,
        )
        applicant = s.legend["applicant"]
        first = applicant["name"].split()[-1]
        assert applicant["voice"] == ("female" if first.endswith(("а", "я")) else "male")
        voices.add(applicant["voice"])
    assert voices == {"female", "male"}


def test_legend_voice_for_old_scenarios() -> None:
    """Сценарии до п. 3.6 без поля voice: голос — по правилу генератора из имени «Фамилия Имя»."""
    assert legend_voice({"name": "Кузнецов Алексей"}) == "male"
    assert legend_voice({"name": "Смирнова Ольга"}) == "female"
    assert legend_voice({"name": "Кузнецов Алексей", "voice": "female"}) == "female"  # записанное — главнее
    assert legend_voice({"name": "Аноним"}) is None and legend_voice({}) is None
