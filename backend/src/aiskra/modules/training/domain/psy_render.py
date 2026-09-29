"""Реплика заявителя с профилем (п. 3.7): офлайн-рендер, ремарки, проверка ответа модели.

Офлайн-рендер берёт шаблон уровня из каталога и подставляет ответ по легенде (`applicant_reply`). Если тема
вопроса закрыта воротами состояния, заявитель отвечает отказной фразой профиля — факт не раскрывается.
Валидатор не пропускает ответ модели, который раскрывает закрытую тему, выходит из роли («я ИИ», «обратитесь на
линию доверия» — известный сбой выровненных моделей, arXiv 2604.23445), содержит стоп-лист или слишком длинный.
"""

from __future__ import annotations

import random
import re
from collections.abc import Mapping
from typing import Any

from aiskra.modules.training.domain.psy import REMARKS, PsyProfile, PsyState

_REMARK_RX = re.compile(r"\[([^\]]{1,40})\]")
ROLE_BREAK = re.compile(
    r"(как (ии|искусственный интеллект|языковая модель)|я (—|-)? ?(ии|бот|модель|ассистент)\b|языков\w+ модел\w+|"
    r"не могу (играть|продолжать)|это (учебн\w+|тренаж\w+)|обратитесь (на|по) (линию|телефон) довери\w+|"
    r"8-800|as an ai|i am an ai|i can.t)",
    re.IGNORECASE,
)
# Стоп-лист: способы суицида и натуралистичные подробности травм в репликах не упоминаются никогда (каталог §5)
STOP_WORDS = re.compile(
    r"(таблет\w*|наглота\w*|повес\w+|вешать\w*|петл\w+|вены|бритв\w+|"
    r"прыгн\w+ с|с крыши|отрав\w+|застрел\w+|кров\w+ хлещет)",
    re.IGNORECASE,
)
SWEAR = re.compile(r"\b(бля\w*|хуй\w*|хуе\w*|пизд\w*|еба\w*|ёба\w*|сука\b|нахуй)\b", re.IGNORECASE)
MAX_WORDS = 40
_REMARK_BY_KEY = {r.replace("ё", "е"): r for r in REMARKS}


def parse_remarks(text: str) -> tuple[str, list[str]]:
    """«[плачет] Он не дышит…» → («Он не дышит…», ["плачет"]). Ремарки вне закрытого списка отбрасываются."""
    remarks: list[str] = []
    for m in _REMARK_RX.finditer(text):
        r = _REMARK_BY_KEY.get(m.group(1).strip().lower().replace("ё", "е"))
        if r and r not in remarks:
            remarks.append(r)
    clean = " ".join(_REMARK_RX.sub(" ", text).split())
    return clean, remarks


def _pick(p: PsyProfile, key: str, rng: random.Random) -> str | None:
    opts = p.offline.get(key)
    return rng.choice(opts) if opts else None


def _short(text: str, words: int = 6) -> str:
    w = text.rstrip(".!?").split()
    return " ".join(w[:words]) if w else text


def _fill(template: str, *, base: str, legend: Mapping[str, Any]) -> str:
    what = str(legend.get("what") or "беда").rstrip(".")
    what_short = what.split(".")[0].split(" (")[0].lower()
    opening = str(legend.get("opening") or f"У нас {what_short}.")
    return (
        template.replace("{base}", base)
        .replace("{short}", _short(base))
        .replace("{what}", what_short)
        .replace("{opening}", opening)
    ).strip()


def opening_line(p: PsyProfile, legend: Mapping[str, Any], rng: random.Random) -> str:
    template = _pick(p, "opening", rng) or "{opening}"
    return _fill(template, base="", legend=legend)


def offline_reply(
    p: PsyProfile,
    s: PsyState,
    *,
    base: str,
    topic: str | None,
    allowed: set[str],
    legend: Mapping[str, Any],
    rng: random.Random,
) -> str:
    """Реплика без модели. `base` — ответ по легенде на заданный вопрос (из `applicant_reply`)."""
    if s.hung_up:
        return "[кладёт трубку]"
    if topic is not None and topic not in allowed:
        return _pick(p, "refuse", rng) or "Я не знаю…"
    if p.stages and s.stage:
        staged = _pick(p, f"stage:{s.stage}", rng)
        # на этапах до раскрытия места заявитель говорит о своём состоянии, а не отвечает по легенде
        if staged is not None and ("{base}" in staged or topic is None or topic == "what"):
            return _fill(staged, base=base, legend=legend)
    for level in (s.level, s.level - 1, s.level + 1, s.level - 2):
        template = _pick(p, str(level), rng)
        if template is not None:
            return _fill(template, base=base, legend=legend)
    return base


def distort_address(p: PsyProfile, s: PsyState, text: str, house: str) -> str:
    """Низкая связность: номер дома «плывёт» («вроде 15 или 17»), пока оператор не подтвердит адрес."""
    if p.coherence >= 0.5 or "address" in s.confirmed or not house.isdigit() or house not in text:
        return text
    return text.replace(house, f"вроде {house}… или {int(house) + 2}", 1)


def blocked_values(legend: Mapping[str, Any], allowed: set[str]) -> list[str]:
    """Значения легенды, которые нельзя произносить в этом состоянии (адрес, этаж, имя…)."""
    a = legend.get("address") or {}
    app = legend.get("applicant") or {}
    out: list[str] = []
    if "address" not in allowed:
        street = str(a.get("street") or "")
        out += [w for w in re.findall(r"[А-ЯЁа-яё]{5,}", street)]
    if "floor" not in allowed:
        out += [f"{a[k]} этаж" for k in ("floor",) if a.get(k)] + [f"квартира {a['flat']}"] * bool(a.get("flat"))
    if "name" not in allowed and app.get("name"):
        out += [str(app["name"]).split()[0]]
    if "phone" not in allowed and app.get("phone"):
        out += [re.sub(r"\D", "", str(app["phone"]))[-7:]]
    return [v for v in out if v]


def validate(text: str, *, legend: Mapping[str, Any], allowed: set[str], intensity: int) -> str | None:
    """Проверка ответа модели. None — годится; иначе причина (реплика заменяется офлайн-ответом)."""
    clean, _ = parse_remarks(text)
    if not clean and "[" not in text:
        return "пустой ответ"
    if ROLE_BREAK.search(text):
        return "выход из роли"
    if STOP_WORDS.search(text):
        return "стоп-лист"
    if intensity <= 1 and SWEAR.search(text):
        return "грубость при интенсивности 1"
    if len(clean.split()) > MAX_WORDS:
        return "слишком длинно"
    low = clean.lower().replace("ё", "е")
    digits = re.sub(r"\D", "", clean)
    for v in blocked_values(legend, allowed):
        vv = v.lower().replace("ё", "е")
        if (vv.isdigit() and vv in digits) or (not vv.isdigit() and vv in low):
            return "раскрыта закрытая тема"
    return None
