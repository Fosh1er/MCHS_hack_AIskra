"""Сценарий учебного вызова (п. 3.2): легенда заявителя, эталон карточки 112, эталон действий ДДС.

Детерминированная часть (тип, признаки, службы, адрес) берётся из справочников правилами; модель пишет только
естественный язык (описание своими словами, первую реплику). Без модели легенда собирается по шаблонам
(`offline_story`) — тренажёр работает в изолированном контуре и в тестах.
"""

from __future__ import annotations

import random
import re
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from aiskra.shared.errors import DomainError


class ScenarioStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    ARCHIVED = "archived"


@dataclass(frozen=True)
class IncidentFacts:
    """Строка классификатора, выбранная для сценария."""

    code: str
    group_id: int
    group_title: str
    card_type: str  # «Что случилось?» (dict_card_types)
    card_type_title: str
    sign1: str | None
    sign2: str | None
    sign3: str | None
    final_type: str | None
    flags: list[str] = field(default_factory=list)  # признаки опросной карты, которые есть у этого типа


@dataclass(frozen=True)
class AddressFacts:
    street: str
    house: str
    building: str
    structure: str
    district: str | None
    district_name: str | None
    okrug: str | None
    lat: float | None
    lon: float | None

    @property
    def label(self) -> str:
        num = (
            self.house
            + (f" к{self.building}" if self.building else "")
            + (f" с{self.structure}" if self.structure else "")
        )
        return f"{self.street}, {num}"


@dataclass(frozen=True)
class ServiceFacts:
    code: str
    short: str
    main: bool
    phone: str


# Статусы заявителя — enums.applicant_status (ApplicantStatus в incidents); здесь коды, чтобы домен был независим.
APPLICANT_STATUSES = ("witness", "victim", "relative", "acquaintance", "participant")
_FIRST = [
    "Анна",
    "Ольга",
    "Мария",
    "Елена",
    "Наталья",
    "Ирина",
    "Сергей",
    "Алексей",
    "Дмитрий",
    "Андрей",
    "Игорь",
    "Олег",
]
_LAST_M = ["Смирнов", "Кузнецов", "Попов", "Волков", "Морозов", "Лебедев", "Козлов", "Новиков", "Павлов", "Соколов"]
_LAST_F = [n + "а" for n in _LAST_M]
EMOTIONS = {
    1: "спокойно",
    2: "немного взволнованно",
    3: "взволнованно",
    4: "в панике, сбивчиво",
    5: "в панике, путается в деталях",
}
FLAG_FACTS = {
    "victims": ("victims", "есть пострадавшие"),
    "threat_to_people": ("danger", "есть угроза людям"),
    "no_access": ("access", "доступа нет, дверь закрыта"),
    "gasified": ("gas", "дом газифицирован"),
    "medical_help": ("medical", "нужна медицинская помощь"),
    "evacuation": ("evacuation", "людей нужно эвакуировать"),
    "offense": ("offense", "похоже на правонарушение"),
    "traffic_blocked": ("traffic", "движение перекрыто"),
}


def synthetic_phone(rng: random.Random) -> str:
    """Учебный номер заявителя: код 9xx, без реальных абонентов (152-ФЗ)."""
    return f"+7 (9{rng.randint(10, 99)}) {rng.randint(100, 999)}-{rng.randint(10, 99)}-{rng.randint(10, 99)}"


def synthetic_person(rng: random.Random) -> tuple[str, str]:
    """Синтетический заявитель: ФИО и голос для озвучки («female» / «male», п. 3.6). Голос задаёт генератор,
    выбирая имя из своего списка, — ничего не угадывается по имени постфактум."""
    first = rng.choice(_FIRST)
    female = first.endswith(("а", "я"))
    return f"{rng.choice(_LAST_F if female else _LAST_M)} {first}", "female" if female else "male"


def _plain(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("/", ", ")).strip().lower()


def humanize(incident: IncidentFacts) -> str:
    """Итоговый тип классификатора → как скажет человек: «пожар: мусор» → «горит мусор»."""
    final = _plain(incident.final_type) or _plain(incident.sign2) or _plain(incident.group_title)
    final = re.sub(r"\s*-\s*", ", ", final)
    for prefix, spoken in (("пожар:", "горит"), ("задымление:", "сильный дым,"), ("угроза:", "угроза")):
        if final.startswith(prefix):
            final = f"{spoken} {final[len(prefix) :].strip()}"
    where = _plain(incident.sign1)
    if where and where not in final and not where.startswith("не отображается"):
        final = f"{final} ({where})"
    return final


def offline_story(incident: IncidentFacts, address: AddressFacts, flags: list[str], difficulty: int) -> dict[str, str]:
    """Описание «своими словами» и первая реплика без модели: из итогового типа, признаков и адреса."""
    what = humanize(incident)
    extra = [FLAG_FACTS[f][1] for f in flags if f in FLAG_FACTS]
    description = what[:1].upper() + what[1:] + (f". {'; '.join(extra).capitalize()}" if extra else "")
    head = what.split(" (")[0]
    opening = {
        1: f"Здравствуйте. У нас {head}. Адрес: {address.label}.",
        2: f"Алло, здравствуйте! Тут {head}, приезжайте, пожалуйста.",
        3: f"Алло! Срочно! {head[:1].upper() + head[1:]}!",
        4: f"Помогите! Тут... {head}! Быстрее!",
        5: f"Алло?! Алло! Скорее, тут {head.split(',')[0]}... я не знаю, что делать!",
    }[max(1, min(difficulty, 5))]
    return {"description": description, "opening": opening, "details": ""}


@dataclass
class Scenario:
    """Сценарий. Эталоны — словари в формате данных карточки (docs/brief/03 §4), чтобы оценка (3.4)
    сравнивала их с `IncidentCardData` поле к полю."""

    title: str
    difficulty: int
    card_type_code: str
    incident_type_code: str
    legend: dict[str, Any]
    reference_card: dict[str, Any]
    reference_dds: dict[str, Any]
    roles: list[str] = field(default_factory=lambda: ["112", "dds"])
    source: str = "ai"
    status: ScenarioStatus = ScenarioStatus.DRAFT
    author_id: UUID | None = None
    approved_by: UUID | None = None
    id: UUID = field(default_factory=uuid4)

    def approve(self, by: UUID) -> None:
        if self.status is ScenarioStatus.ARCHIVED:
            raise DomainError("Сценарий в архиве", code="scenario_archived")
        self.status = ScenarioStatus.APPROVED
        self.approved_by = by

    def archive(self) -> None:
        self.status = ScenarioStatus.ARCHIVED


def build_scenario(
    *,
    incident: IncidentFacts,
    address: AddressFacts,
    services: list[ServiceFacts],
    story: dict[str, str],
    flags: list[str],
    difficulty: int,
    rng: random.Random,
    source: str,
    author_id: UUID | None,
) -> Scenario:
    """Собрать сценарий: легенда (что знает заявитель) + эталоны 112 и ДДС."""
    if not 1 <= difficulty <= 5:
        raise DomainError("Сложность — от 1 до 5", code="bad_difficulty")
    victims = "victims" in flags
    victims_count = rng.randint(1, 3) if victims else 0
    name, voice = synthetic_person(rng)
    status = rng.choice(APPLICANT_STATUSES[: 3 if difficulty < 3 else 5])
    phone = synthetic_phone(rng)
    floor = str(rng.randint(1, 16)) if "дом" in _plain(incident.sign1) or "квартир" in _plain(incident.sign2) else ""
    flat = str(rng.randint(1, 300)) if floor else ""
    path = [s for s in (incident.sign1, incident.sign2, incident.sign3) if s]
    legend = {
        "applicant": {"name": name, "status": status, "phone": phone, "voice": voice},
        "address": {
            **asdict(address),
            "label": address.label,
            "floor": floor,
            "flat": flat,
            "entrance": str(rng.randint(1, 8)) if floor else "",
        },
        "what": story.get("description") or incident.final_type or incident.group_title,
        "details": story.get("details", ""),
        "opening": story.get("opening", ""),
        "emotion": EMOTIONS[difficulty],
        "facts": {FLAG_FACTS[f][0]: FLAG_FACTS[f][1] for f in flags},
        "victims": {"has": victims, "count": victims_count},
        "difficulty": difficulty,
    }
    main = next((s for s in services if s.main), services[0] if services else None)
    reference_card = {
        "card_types": [incident.card_type],
        "incident_types": [incident.code],
        "questionnaire": {incident.card_type: {f"Признак {i + 1}": v for i, v in enumerate(path)}},
        "card_flags": flags,
        "applicant": {"name": name, "status": status},
        "phones": {"aon": phone},
        "victims": {"has": victims, "count": victims_count},
        "address": {
            "street": address.street,
            "house": address.house,
            "building": address.building,
            "structure": address.structure,
            "okrug": address.okrug,
            "district": address.district,
            "floor": floor,
            "flat": flat,
            "lat": address.lat,
            "lon": address.lon,
        },
        "description_keywords": [w for w in re.findall(r"[а-яё]{4,}", _plain(" ".join(path)))][:6],
        "services": [{"code": s.code, "short": s.short, "main": s.main} for s in services],
        "final_type": incident.final_type,
    }
    reference_dds = {
        "main_service": main.code if main else None,
        "first_status": "accepted",
        "statuses": ["accepted", "response_started", "arrived", "works_in_progress", "works_completed"],
        "order_no_required": True,
        "expected_calls": ["brigade"],
        "phrases": ["Сообщение принято, дежурная бригада направлена на место"],
    }
    place = address.district_name or address.street
    title = f"{incident.card_type_title}: {incident.final_type or incident.group_title} — {place}"
    return Scenario(
        title=title[:255],
        difficulty=difficulty,
        card_type_code=incident.card_type,
        incident_type_code=incident.code,
        legend=legend,
        reference_card=reference_card,
        reference_dds=reference_dds,
        source=source,
        author_id=author_id,
    )
