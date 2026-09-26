"""Ролевые агенты диалога (п. 3.3): офлайн-режим без языковой модели.

Заявитель отвечает только на то, о чём спросили, из своей легенды — не выдаёт лишнего и не знает эталона
(тип классификатора, службы). Старший группы докладывает по текущему статусу службы (#691). Диспетчер смежной
службы подтверждает получение. С подключённой моделью те же роли играет LLM (промпты в `aiskra/ai/prompts`),
а этот модуль задаёт факты, которые ей разрешено раскрыть.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Вопрос оператора → тема легенды. Порядок важен: первая подходящая тема.
TOPICS: list[tuple[str, tuple[str, ...]]] = [
    ("address", ("адрес", "где", "улиц", "дом", "куда", "место", "находит", "район")),
    ("floor", ("этаж", "подъезд", "квартир", "код", "домофон")),
    ("name", ("зовут", "имя", "фамил", "фио", "представ", "кто вы", "как к вам")),
    ("phone", ("телефон", "номер", "перезвон", "связ")),
    ("victims", ("пострада", "ранен", "жертв", "люди", "человек", "дети", "кто-то")),
    ("danger", ("угроз", "опасн", "распростран", "огонь", "пламя", "дым")),
    ("access", ("доступ", "дверь", "попасть", "откры", "закрыт")),
    ("gas", ("газ",)),
    ("status", ("кем приход", "очевид", "родствен", "кто вам", "свидетел")),
    ("what", ("что случ", "что произош", "что у вас", "опишите", "расскаж", "подробн", "что вид", "что там")),
]
STATUS_WORDS = {
    "witness": "я просто мимо шёл(шла), увидел(а)",
    "victim": "это со мной случилось",
    "relative": "это мой родственник",
    "acquaintance": "это мой знакомый",
    "participant": "я участник",
    "child": "я ребёнок",
}
GREETING = re.compile(r"^\s*(служба\s*112|112|здравствуйте|алло|слушаю)", re.IGNORECASE)


def people(n: int) -> str:
    """«1 человек», «2 человека», «5 человек», «11 человек», «21 человек»."""
    tail = n % 100
    word = "человека" if n % 10 in (2, 3, 4) and not 12 <= tail <= 14 else "человек"
    return f"{n} {word}"


def topic_of(question: str) -> str | None:
    q = question.lower().replace("ё", "е")
    for topic, keys in TOPICS:
        if any(k in q for k in keys):
            return topic
    return None


@dataclass
class ApplicantReply:
    text: str
    topic: str | None
    revealed: list[str] = field(default_factory=list)


def applicant_reply(legend: dict[str, Any], question: str, revealed: list[str]) -> ApplicantReply:
    """Ответ заявителя по легенде. Неясный вопрос — заявитель переспрашивает или повторяет главное."""
    a = legend.get("address", {})
    app = legend.get("applicant", {})
    facts = legend.get("facts", {})
    victims = legend.get("victims", {})
    topic = topic_of(question)
    if topic is None and GREETING.match(question) and "opening" not in revealed:
        topic = "opening"
    text = {
        "opening": legend.get("opening") or f"Здравствуйте, у нас {legend.get('what', 'происшествие')}.",
        "address": f"{a.get('label', 'Не знаю точно')}"
        + (f", район {a['district_name']}" if a.get("district_name") else ""),
        "floor": (
            f"{a['entrance']} подъезд, {a['floor']} этаж, квартира {a['flat']}"
            if a.get("floor")
            else "Это на улице, не в квартире."
        ),
        "name": app.get("name", "Не хочу называть"),
        "phone": f"Мой номер {app.get('phone', 'этот же')}.",
        "victims": (
            f"Да, пострадавшие есть, {people(int(victims.get('count') or 1))}."
            if victims.get("has")
            else "Нет, вроде никто не пострадал."
        ),
        "danger": facts.get("danger") or "Не знаю, вроде пока не распространяется.",
        "access": facts.get("access") or "Не знаю про доступ.",
        "gas": facts.get("gas") or "Про газ не знаю.",
        "status": STATUS_WORDS.get(app.get("status", ""), "Я просто сообщаю."),
        "what": f"{legend.get('what', 'Происшествие')}." + (f" {legend['details']}" if legend.get("details") else ""),
    }.get(topic or "")
    if text is None:
        text = "Что? Повторите, пожалуйста… " + (
            legend.get("what", "") if "what" not in revealed else "Я же говорю, приезжайте скорее!"
        )
    return ApplicantReply(
        text=text, topic=topic, revealed=[*revealed, topic] if topic and topic not in revealed else revealed
    )


BRIGADE_REPORTS = {
    "added": "Карточку ещё не получили. Какой адрес?",
    "received": "Слушаю. Ждём решения — выезжать?",
    "accepted": "Принял, наряд {order}. Выезжаем, будем минут через 10.",
    "response_started": "Выехали, в пути. Прибытие минут через 5–7.",
    "arrived": "Прибыли на место, оцениваем обстановку.",
    "works_in_progress": "Работаем на месте. Обстановка под контролем, доложу по завершении.",
    "works_completed": "Работы завершены, выезжаем с адреса.",
    "works_refused": "Работы не выполняем — причина в карточке.",
    "rejected": "Карточку не приняли, на выезд не едем.",
}


def brigade_reply(context: dict[str, Any], question: str) -> str:
    """Доклад старшего группы реагирования по текущему статусу службы (#691: «старший звонит в ДДС и докладывает»)."""
    status = context.get("service_status", "received")
    order = context.get("order_no") or "без номера"
    base = BRIGADE_REPORTS.get(status, "Слушаю вас.").format(order=order)
    q = question.lower()
    if "адрес" in q:
        return f"{base} Адрес: {context.get('address') or 'уточните'}."
    if "пострада" in q:
        return f"{base} Пострадавших: {context.get('victims', 'не знаю')}."
    return base


def service_reply(context: dict[str, Any], question: str) -> str:
    """Диспетчер смежной службы: подтверждает, что карточка у них, и называет свой статус."""
    return (
        f"Дежурный {context.get('service_short', 'службы')} слушает. Карточку {context.get('card_number', '')} видим, "
        f"статус у нас «{context.get('service_status_title', 'получена')}». Взаимодействуем."
    )
