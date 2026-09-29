"""Автооценка по эталону (п. 3.4): детерминированные правила. Формулы — в сопроводительной документации
(«Методы обработки данных»), здесь — их единственная реализация.

Каждый критерий даёт балл 0…1 и список ошибок с пояснением для обучающегося. Итог — взвешенное среднее по
критериям, которые удалось проверить (`checked`), в баллах 0…100. Веса и нормативы настраиваются (ТЗ: «критерии
успешности, пороги»), значения по умолчанию — ниже. Критерии ИИ-судьи добавляются отдельно; без модели они
помечаются «не проверено» и в итог не входят — оценка остаётся воспроизводимой.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

CARD_NORM_SECONDS = 75  # опрос до карточки, доступной ДДС, в среднем 75 с — ПП РФ № 1931, п. 9 «р» (docs/research)
DDS_NORM_SECONDS = 30  # норматив решения ДДС «Принята / Не принята» (#709, ТЗ)
PASS_THRESHOLD = 70  # порог «зачтено», баллы

WEIGHTS_112: dict[str, float] = {
    "type": 3,
    "services": 2,
    "address": 2,
    "flags": 1,
    "applicant": 1,
    "victims": 1,
    "description": 1,
    "interview": 1,
    "timing": 1,
    "description_meaning": 1,
    "grammar": 0.5,
    # п. 3.6: информативно, пока показатель не сверят эксперты (3.5); вес можно задать в настройках занятия
    "caller_care": 0,
}
WEIGHTS_DDS: dict[str, float] = {
    "decision": 3,
    "reaction": 2,
    "chain": 2,
    "order_no": 1,
    "comments": 1,
    "calls": 1,
    "regulation": 1,
    "grammar": 0.5,
}
TITLES: dict[str, str] = {
    "type": "Тип происшествия",
    "services": "Службы",
    "address": "Адрес",
    "flags": "Признаки опросной карты",
    "applicant": "Заявитель",
    "victims": "Пострадавшие",
    "description": "Описание: ключевые факты",
    "interview": "Полнота опроса заявителя",
    "timing": "Время заполнения",
    "description_meaning": "Описание: смысл (ИИ)",
    "grammar": "Грамотность (ИИ)",
    "caller_care": "Работа с заявителем (информативно)",
    "decision": "Решение «Принята / Не принята»",
    "reaction": "Время реакции",
    "chain": "Порядок и полнота статусов",
    "order_no": "Номер наряда",
    "comments": "Комментарии к статусам",
    "calls": "Звонки",
    "regulation": "Регламентность формулировок (ИИ)",
}
INTERVIEW_TOPICS = {"address": "адрес", "what": "что случилось", "victims": "пострадавшие"}


@dataclass(frozen=True)
class CallerFacts:
    """Как менялось состояние ИИ-заявителя в разговоре (п. 3.6): напряжение 0–10 у первой и последней его реплики
    и что сказал оператор — по кодам причин из снимков состояния."""

    start: int
    end: int
    calming: int = 0
    invalidating: list[str] = field(default_factory=list)  # сработавшие фразы: «успокойтесь», «не кричите»…
    pressure: list[str] = field(default_factory=list)


def caller_care(f: CallerFacts) -> Criterion:
    """Работа с эмоциональным заявителем: 1 — напряжение не выросло и обесценивания не было; −0,1 за каждый пункт
    роста напряжения, −0,15 за каждую обесценивающую реплику, −0,05 за давление. Вес 0: показатель информативный."""
    grew = max(0, f.end - f.start)
    score = max(0.0, 1 - 0.1 * grew - 0.15 * len(f.invalidating) - 0.05 * len(f.pressure))
    c = Criterion("caller_care", round(score, 3), note=f"напряжение заявителя {f.start} → {f.end} из 10")
    if grew:
        c.errors.append(f"заявитель стал напряжённее: {f.start} → {f.end} из 10")
    if f.invalidating:
        c.errors.append("обесценивающие фразы: " + ", ".join(f"«{p}»" for p in dict.fromkeys(f.invalidating)))
    return c


CHAIN = ["accepted", "response_started", "arrived", "works_in_progress", "works_completed"]


@dataclass
class Criterion:
    key: str
    score: float | None  # None — не проверено (нет эталона или модели)
    errors: list[str] = field(default_factory=list)
    note: str = ""
    # критическая ошибка (п. 3.5): обучающийся отправил бы не те силы или не туда — «не зачтено» при любом балле
    critical: bool = False

    @property
    def title(self) -> str:
        return TITLES.get(self.key, self.key)


@dataclass
class Result:
    role: str  # 112 | dds
    criteria: list[Criterion]
    score: float
    passed: bool
    has_reference: bool
    stats: dict[str, Any] = field(default_factory=dict)

    @property
    def errors(self) -> list[str]:
        return [f"{c.title}: {e}" for c in self.criteria for e in c.errors]

    @property
    def critical(self) -> list[str]:
        return [c.key for c in self.criteria if c.critical]


def norm_text(s: str | None) -> str:
    s = (s or "").lower().replace("ё", "е")
    s = re.sub(
        r"\b(улица|ул|проспект|пр-т|переулок|пер|шоссе|ш|бульвар|б-р|проезд|пр-д|площадь|пл|набережная|наб)\b\.?",
        " ",
        s,
    )
    return re.sub(r"[^а-яa-z0-9]+", " ", s).strip()


def norm_words(s: str | None) -> str:
    """Нормализация свободного текста (описание): регистр, «ё», знаки. В отличие от `norm_text` слова «улица»,
    «набережная» и т. п. не вырезаются — иначе такие ключевые факты эталона не найти (п. 3.5, бенчмарк)."""
    s = (s or "").lower().replace("ё", "е")
    return re.sub(r"[^а-яa-z0-9]+", " ", s).strip()


def f1(given: set[str], expected: set[str]) -> tuple[float, set[str], set[str]]:
    """F1 по множествам; возвращает также пропущенные и лишние элементы."""
    if not expected and not given:
        return 1.0, set(), set()
    tp = len(given & expected)
    precision = tp / len(given) if given else 0.0
    recall = tp / len(expected) if expected else 1.0
    score = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return score, expected - given, given - expected


def timing_score(seconds: float, norm: float) -> float:
    """1 — в нормативе; дальше линейно до 0 при тройном нормативе."""
    if seconds <= norm:
        return 1.0
    return max(0.0, 1 - (seconds - norm) / (2 * norm))


def total(criteria: list[Criterion], weights: dict[str, float]) -> float:
    checked = [(c.score, weights.get(c.key, 1.0)) for c in criteria if c.score is not None]
    wsum = sum(w for _, w in checked)
    return round(100 * sum(s * w for s, w in checked) / wsum, 1) if wsum else 0.0


# ------------------------------------------------------------------ карточка 112


def _group(code: str | None) -> str:
    return code[:-6] if code and len(code) > 6 else ""


def assess_card_112(
    card: dict[str, Any],
    services: list[str],
    processing_s: float | None,
    reference: dict[str, Any] | None,
    asked_topics: set[str] | None,
    *,
    norm_seconds: float = CARD_NORM_SECONDS,
    names: dict[str, str] | None = None,
    flag_names: dict[str, str] | None = None,
    spoken: str | None = None,
    caller: CallerFacts | None = None,
) -> list[Criterion]:
    """Критерии карточки 112. `names`, `flag_names` — коды служб и признаков → названия (понятные сообщения);
    `spoken` — что сообщил заявитель: ключевые факты описания учитываются, только если они прозвучали."""
    names = names or {}
    fnames = flag_names or {}
    out: list[Criterion] = []
    ref = reference or {}
    has_ref = bool(ref)
    if processing_s is not None:
        c = Criterion("timing", timing_score(processing_s, norm_seconds))
        if processing_s > norm_seconds:
            c.errors.append(f"карточка заполнена за {int(processing_s)} с при нормативе {int(norm_seconds)} с")
        out.append(c)
    if not has_ref:
        return out

    # тип: точный конечный тип — 1; тот же «Что случилось?» или группа — 0,5
    given_types = list(card.get("incident_types") or [])
    exp_types = list(ref.get("incident_types") or [])
    c = Criterion("type", 0.0)
    if given_types and exp_types and given_types[0] == exp_types[0]:
        c.score = 1.0
    elif set(card.get("card_types") or []) & set(ref.get("card_types") or []) or (
        given_types and exp_types and _group(given_types[0]) == _group(exp_types[0])
    ):
        c.score = 0.5
        c.errors.append(f"выбран близкий, но не тот тип; эталон — «{ref.get('final_type') or exp_types[0]}»")
    else:
        c.errors.append(f"неверный тип; эталон — «{ref.get('final_type') or (exp_types[0] if exp_types else '?')}»")
        c.critical = True  # другая группа — другие силы и алгоритм реагирования
    out.append(c)

    score, missing, extra = f1(set(services), {s["code"] for s in ref.get("services", [])})
    c = Criterion("services", score)
    if missing:
        c.errors.append("не направлено в: " + ", ".join(sorted(names.get(m, m) for m in missing)))
    if extra:
        c.errors.append("лишние службы: " + ", ".join(sorted(names.get(x, x) for x in extra)))
    main = next((s["code"] for s in ref.get("services", []) if s.get("main")), None)
    if main and main not in services:
        c.errors.append(f"нет основной службы «{names.get(main, main)}»")
        c.critical = True
    out.append(c)

    a, ra = card.get("address") or {}, ref.get("address") or {}
    street_ok = norm_text(a.get("street")) == norm_text(ra.get("street")) and bool(ra.get("street"))
    house_ok = norm_text(a.get("house")) == norm_text(ra.get("house"))
    district_ok = bool(a.get("district")) and a.get("district") == ra.get("district")
    c = Criterion(
        "address",
        round((0.6 if street_ok else 0) + (0.3 if street_ok and house_ok else 0) + (0.1 if district_ok else 0), 3),
    )
    if not street_ok:
        c.errors.append(f"улица не совпадает с эталоном «{ra.get('street')}»")
        c.critical = bool(ra.get("street"))  # силы уедут не туда
    elif not house_ok:
        c.errors.append(f"номер дома не совпадает (эталон {ra.get('house')})")
    if not district_ok:
        c.errors.append("не указан или неверен район — не подключатся территориальные службы")
    out.append(c)

    score, missing, extra = f1(set(card.get("card_flags") or []), set(ref.get("card_flags") or []))
    c = Criterion("flags", score)
    if missing:
        c.errors.append("не отмечены признаки: " + ", ".join(sorted(fnames.get(m, m) for m in missing)))
    if extra:
        c.errors.append("лишние признаки: " + ", ".join(sorted(fnames.get(x, x) for x in extra)))
    out.append(c)

    ap, rap = card.get("applicant") or {}, ref.get("applicant") or {}
    name_ok = norm_text(rap.get("name")).split()[:1] == norm_text(ap.get("name")).split()[:1] and bool(ap.get("name"))
    status_ok = ap.get("status") == rap.get("status")
    c = Criterion("applicant", 0.5 * name_ok + 0.5 * status_ok)
    if not name_ok:
        c.errors.append("ФИО заявителя не записано или записано с ошибкой")
    if not status_ok:
        c.errors.append("неверный статус заявителя")
    out.append(c)

    v, rv = card.get("victims") or {}, ref.get("victims") or {}
    has_ok = bool(v.get("has")) == bool(rv.get("has"))
    count_ok = not rv.get("has") or int(v.get("count") or 0) == int(rv.get("count") or 0)
    c = Criterion("victims", 0.7 * has_ok + 0.3 * (has_ok and count_ok))
    if not has_ok:
        c.errors.append(
            "в легенде есть пострадавшие, а в карточке — нет"
            if rv.get("has")
            else "в карточке отмечены пострадавшие, которых нет"
        )
        c.critical = bool(rv.get("has"))  # без отметки не будет вызвана скорая
    elif not count_ok:
        c.errors.append(f"неверное количество пострадавших (эталон {rv.get('count')})")
    out.append(c)

    words = [w for w in ref.get("description_keywords", []) if w]
    if spoken is not None:  # п. 3.5: нельзя требовать в описании то, чего заявитель не говорил
        heard = norm_words(spoken)
        words = [w for w in words if norm_words(w)[:5] in heard]
    text = norm_words(card.get("description"))
    if words:
        hit = [w for w in words if norm_words(w)[:5] in text]
        c = Criterion("description", len(hit) / len(words))
        miss = [w for w in words if w not in hit]
        if miss:
            c.errors.append("в описании нет ключевых фактов: " + ", ".join(miss[:4]))
        if not text:
            c.errors.append("описание со слов заявителя пустое")
        out.append(c)

    if asked_topics is not None:
        asked = asked_topics & set(INTERVIEW_TOPICS)
        c = Criterion("interview", len(asked) / len(INTERVIEW_TOPICS))
        miss = [INTERVIEW_TOPICS[t] for t in INTERVIEW_TOPICS if t not in asked]
        if miss:
            c.errors.append("не уточнено у заявителя: " + ", ".join(miss))
        out.append(c)
    if caller is not None:  # разговор с ИИ-заявителем шёл с состоянием (п. 3.6)
        out.append(caller_care(caller))
    return out


# ------------------------------------------------------------------ АРМ ДДС


@dataclass(frozen=True)
class StatusStep:
    status: str
    at: datetime | None
    order_no: str | None
    comment: str | None


def assess_dds(
    history: list[StatusStep],
    added_at: datetime | None,
    reference: dict[str, Any] | None,
    calls: list[str],
    *,
    norm_seconds: float = DDS_NORM_SECONDS,
) -> list[Criterion]:
    """Критерии работы диспетчера ДДС по своей службе: история статусов и звонки."""
    ref = reference or {}
    steps = [h for h in history if h.status not in ("added", "received")]
    out: list[Criterion] = []
    first = steps[0] if steps else None
    expected_first = ref.get("first_status", "accepted")

    c = Criterion("decision", 0.0, critical=True)
    if first is None:
        c.errors.append("решение по карточке не принято")
    elif first.status == expected_first:
        c.score, c.critical = 1.0, False
    else:
        c.errors.append(
            "карточка не принята, хотя по эталону служба должна реагировать"
            if expected_first == "accepted"
            else "карточка принята, хотя эталон — «Не принята»"
        )
    out.append(c)

    if first is not None and first.at and added_at:
        secs = max(0.0, (first.at - added_at).total_seconds())
        c = Criterion("reaction", timing_score(secs, norm_seconds), critical=secs > 3 * norm_seconds)
        if secs > norm_seconds:
            c.errors.append(f"решение принято через {int(secs)} с при нормативе {int(norm_seconds)} с")
        out.append(c)

    if first is not None and first.status == "accepted":
        done = [s.status for s in steps]
        reached = max((CHAIN.index(s) for s in done if s in CHAIN), default=0)
        order = [CHAIN.index(s) for s in done if s in CHAIN]
        in_order = order == sorted(order)
        refused = "works_refused" in done
        c = Criterion("chain", (reached + 1) / len(CHAIN) * (1.0 if in_order else 0.7))
        if refused:
            c.score = 1.0 if (c.score or 0) > 0 else 0.5
            c.note = "работы прекращены «Отказом от выполнения работ»"
        elif CHAIN[-1] not in done:
            c.errors.append(f"работы не доведены до «Работы завершены» (последний статус — {done[-1]})")
        if not in_order:
            c.errors.append("статусы проставлены не по порядку")
        out.append(c)

        c = Criterion("order_no", 1.0 if first.order_no else 0.0)
        if not first.order_no:
            c.errors.append("не указан номер наряда при «Принята»")
        out.append(c)

    if steps:
        with_comment = [s for s in steps if (s.comment or "").strip()]
        c = Criterion("comments", len(with_comment) / len(steps))
        if len(with_comment) < len(steps):
            c.errors.append(f"комментарий есть у {len(with_comment)} из {len(steps)} статусов")
        out.append(c)

    expected_calls = ref.get("expected_calls", ["brigade"]) if first is not None and first.status == "accepted" else []
    if expected_calls:
        made = set(calls)
        c = Criterion("calls", len(made & set(expected_calls)) / len(expected_calls))
        if "brigade" in expected_calls and "brigade" not in made:
            c.errors.append("не было связи со старшим группы — ход работ не подтверждён")
        out.append(c)
    return out


def finish(
    role: str,
    criteria: list[Criterion],
    weights: dict[str, float],
    has_reference: bool,
    threshold: float = PASS_THRESHOLD,
    stats: dict[str, Any] | None = None,
) -> Result:
    score = total(criteria, weights)
    if any(c.critical for c in criteria):  # критическая ошибка — «не зачтено», балл ниже порога (п. 3.5)
        score = min(score, max(0.0, threshold - 1))
    return Result(
        role=role,
        criteria=criteria,
        score=score,
        passed=score >= threshold and not any(c.critical for c in criteria),
        has_reference=has_reference,
        stats=stats or {},
    )
