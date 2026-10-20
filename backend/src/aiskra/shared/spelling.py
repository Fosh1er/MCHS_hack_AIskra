"""Проверка грамотности правилами — без модели и одинаково на любом стенде.

- После ручной правки сценария (ТЗ 3.6 «принудительная проверка грамматики»): повтор слова подряд, латинская буква
  внутри русского слова, пробел перед знаком препинания, двойной пробел, строчная буква в начале предложения,
  нет точки в конце, незакрытые кавычки и скобки.
- Текст обучающегося — описание в карточке 112 и комментарии ДДС (ТЗ 4.5, 5.10), когда ИИ-судья не подключён:
  те же правила, кроме «заглавной в начале» и «точки в конце» (в АРМ пишут кратко: «запах в кухне и ванной»),
  плюс частые орфографические ошибки из словаря `TYPOS`.
Если подключена модель, прикладной слой добавляет её замечания.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

LAT_IN_CYR = re.compile(r"\b(?=\w*[а-яё])(?=\w*[a-z])[а-яёa-z]+\b", re.IGNORECASE)
LOOKALIKE = str.maketrans("aceopxyAEKMHOPCTXB", "асеорхуАЕКМНОРСТХВ")
REPEAT = re.compile(r"\b(\w{2,})\s+\1\b", re.IGNORECASE)
SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.!?;:])")
SENTENCE = re.compile(r"(?:^|[.!?]\s+)([а-яёa-z])")


@dataclass(frozen=True)
class Remark:
    field: str
    quote: str
    fix: str
    rule: str


def check_text(field: str, text: str) -> list[Remark]:
    """Замечания к одному полю легенды; пустой список — ошибок по правилам нет."""
    t = text.strip()
    if not t:
        return []
    out: list[Remark] = []
    for m in REPEAT.finditer(t):
        out.append(Remark(field, m.group(0), m.group(1), "повтор слова"))
    for m in LAT_IN_CYR.finditer(t):
        word = m.group(0)
        out.append(Remark(field, word, word.translate(LOOKALIKE), "латинская буква в русском слове"))
    for m in SPACE_BEFORE_PUNCT.finditer(t):
        out.append(Remark(field, m.group(0), m.group(1), "пробел перед знаком препинания"))
    if "  " in t:
        out.append(Remark(field, "  ", " ", "двойной пробел"))
    for m in SENTENCE.finditer(t):
        start = max(0, m.start(1) - 12)
        out.append(
            Remark(field, t[start : m.end(1) + 12].strip(), m.group(1).upper(), "строчная буква в начале предложения")
        )
    if field != "title" and t[-1] not in '.!?…»"':
        out.append(Remark(field, t[-20:], t[-20:] + ".", "нет знака препинания в конце"))
    for a, b in (("«", "»"), ("(", ")")):
        if t.count(a) != t.count(b):
            out.append(Remark(field, a if t.count(a) > t.count(b) else b, f"{a}…{b}", "незакрытые кавычки или скобки"))
    return out


def check_legend(fields: dict[str, str]) -> list[Remark]:
    return [r for name, value in fields.items() for r in check_text(name, value or "")]


# частые ошибки в словах, которые пишут в карточке и комментариях; ключ — ошибочное написание (нижний регистр)
TYPOS: dict[str, str] = {
    "здраствуйте": "здравствуйте",
    "пожалуста": "пожалуйста",
    "извените": "извините",
    "сдесь": "здесь",
    "щас": "сейчас",
    "чуствует": "чувствует",
    "чуствовать": "чувствовать",
    "учасник": "участник",
    "агенство": "агентство",
    "будте": "будьте",
    "ложит": "кладёт",
    "ихний": "их",
    "пострадавщий": "пострадавший",
    "пострадавщие": "пострадавшие",
    "пастрадавший": "пострадавший",
    "скорея": "скорая",
    "задымленее": "задымление",
    "возгарание": "возгорание",
    "возгараний": "возгораний",
    "потерпевщий": "потерпевший",
    "пожарнные": "пожарные",
    "бригадда": "бригада",
    "диспечер": "диспетчер",
    "дежурнная": "дежурная",
    "направленна": "направлена",
    "сообшение": "сообщение",
    "сообщенние": "сообщение",
    "прибытее": "прибытие",
    "вобщем": "в общем",
    "вообщем": "в общем",
    "както": "как-то",
    "кто то": "кто-то",
    "что то": "что-то",
    "где то": "где-то",
}
WORD = re.compile(r"[а-яё]+(?:\s(?:то|нибудь))?", re.IGNORECASE)
LOOSE_RULES = ("строчная буква в начале предложения", "нет знака препинания в конце")


def check_operator_text(field: str, text: str) -> list[Remark]:
    """Замечания к тексту обучающегося (описание, комментарий к статусу) без модели (ТЗ 4.5, 5.10)."""
    out = [r for r in check_text(field, text) if r.rule not in LOOSE_RULES]
    for m in WORD.finditer(text):
        word = m.group(0)
        fix = TYPOS.get(word.lower())
        if fix is not None:
            out.append(Remark(field, word, fix, "орфография"))
    return list(dict.fromkeys(out))
