"""Отзыв преподавателя по занятию (п. 4.7): факты для черновика и черновик по правилам.

Структура отзыва отвечает на три вопроса хорошей обратной связи (Hattie & Timperley, 2007):
- как прошло — итог;
- что получилось и что подтянуть;
- что делать дальше — следующий шаг.

По Shute (2008) отзыв конкретный и небольшими порциями: не больше трёх пунктов «подтянуть», примеры — из своих
карточек, без сравнения с другими обучающимися. Функции чистые: одинаковые факты — одинаковый черновик.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from aiskra.modules.assessment.domain.analytics import error_key
from aiskra.modules.assessment.domain.recommendations import RECOMMENDATIONS
from aiskra.modules.assessment.domain.scoring import TITLES, WEIGHTS_112, WEIGHTS_DDS

STRONG = 0.85  # критерий «получилось» — тот же порог, что у слабого места в рекомендациях (п. 5.1)
MAX_FOCUS = 3
MAX_STRENGTHS = 2
MIN_TEXT, MAX_TEXT = 10, 3000

# Что получилось — по-человечески, а не названием критерия
STRENGTHS: dict[str, str] = {
    "type": "Тип происшествия выбираете верно",
    "services": "Службы направляете правильно",
    "address": "Адрес заполняете точно",
    "flags": "Опросную карту проходите полностью",
    "applicant": "Данные заявителя записываете",
    "victims": "О пострадавших спрашиваете",
    "description": "В описании — ключевые факты",
    "interview": "Опрос ведёте в правильном порядке",
    "timing": "Укладываетесь в норматив времени",
    "description_meaning": "Описание передаёт смысл рассказа заявителя",
    "grammar": "Пишете грамотно",
    "caller_care": "Спокойно работаете со взволнованным заявителем",
    "decision": "Решение «Принята / Не принята» принимаете верно",
    "reaction": "Решение принимаете в норматив",
    "chain": "Статусы ведёте по порядку до конца",
    "order_no": "Номер наряда указываете",
    "comments": "Комментарии к статусам пишете",
    "calls": "Со старшим группы созваниваетесь",
    "regulation": "Формулировки регламентные",
}
_WEIGHT = {**WEIGHTS_DDS, **WEIGHTS_112}


@dataclass(frozen=True)
class CardFacts:
    """Карточка занятия глазами отзыва: из отчёта по занятию (п. 4.3)."""

    number: int
    score: float | None  # None — не оценена
    passed: bool | None
    processing_s: float | None  # время заполнения карточки 112; у ДДС время — в критерии «Время реакции»
    norm_s: float
    errors: list[str]  # «Критерий: замечание»
    criteria: dict[str, float | None]  # None — критерий не проверялся
    critical: list[str] = field(default_factory=list)  # названия критериев с критической ошибкой
    expert_comment: str = ""


@dataclass(frozen=True)
class PreviousFeedback:
    """Прошлый отзыв этого преподавателя этому обучающемуся: что просили подтянуть и какие были средние."""

    session_title: str
    focus: list[str]
    criteria: dict[str, float]


@dataclass(frozen=True)
class Focus:
    key: str
    title: str
    average: float
    example: str  # самое частое замечание по критерию
    cards: list[int]
    advice: str
    critical: bool = False


@dataclass(frozen=True)
class Progress:
    key: str
    title: str
    before: float
    now: float


@dataclass(frozen=True)
class FeedbackFacts:
    session_title: str
    threshold: float
    cards: int
    assessed: int
    avg_score: float | None
    passed: int
    timed: int  # карточек 112 со временем
    in_norm: int
    norm_s: float | None
    criteria: dict[str, float]  # средние по критериям, 0–1
    strengths: list[tuple[str, float]]
    focus: list[Focus]
    progress: list[Progress]
    expert_comments: list[tuple[int, str]]


@dataclass(frozen=True)
class DraftParts:
    """Части отзыва. Их заполняют правила или модель, в текст собирает `compose` — вид всегда одинаковый."""

    summary: str
    progress: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    improve: list[str] = field(default_factory=list)
    next_step: str = ""


def pct(x: float) -> str:
    return f"{round(x * 100)} %"


def _num(x: float) -> str:
    return f"{round(x, 1):g}".replace(".", ",")


def cards_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "карточка"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "карточки"
    return "карточек"


def _numbers(cards: list[int]) -> str:
    return ("карточка № " if len(cards) == 1 else "карточки № ") + ", ".join(str(n) for n in cards)


def _focus(key: str, average: float, cards: list[CardFacts]) -> Focus:
    title = TITLES.get(key, key)
    prefix = f"{title}: "
    texts = [(c.number, e[len(prefix) :]) for c in cards for e in c.errors if e.startswith(prefix)]
    counts = Counter(error_key(title, t) for _, t in texts)
    top = counts.most_common(1)[0][0] if counts else None
    example = next((t for _, t in texts if error_key(title, t) == top), "")
    numbers = sorted({n for n, _ in texts}) or sorted(
        c.number for c in cards if (c.criteria.get(key) is not None and (c.criteria[key] or 0) < 1)
    )
    return Focus(
        key=key,
        title=title,
        average=round(average, 2),
        example=example,
        cards=numbers,
        advice=RECOMMENDATIONS.get(key, ""),
        critical=any(title in c.critical for c in cards),
    )


def summarize(
    title: str, threshold: float, cards: list[CardFacts], previous: PreviousFeedback | None = None
) -> FeedbackFacts:
    """Факты для отзыва: итог, сильные стороны, до трёх слабых мест (критические — первыми), прогресс с прошлого."""
    assessed = [c for c in cards if c.score is not None]
    per_key: dict[str, list[float]] = {}
    for c in assessed:
        for k, v in c.criteria.items():
            if v is not None:
                per_key.setdefault(k, []).append(float(v))
    averages = {k: round(sum(v) / len(v), 2) for k, v in per_key.items()}
    critical_keys = {k for k in averages if any(TITLES.get(k, k) in c.critical for c in assessed)}
    # «подтянуть» — всё, где были потери: сначала критические, потом от худшего. Даже при высоком балле обучающийся
    # узнаёт о конкретных промахах («номер дома не совпадает»), а не только «так держать»
    weak = sorted(
        (k for k, v in averages.items() if v < 1 or k in critical_keys),
        key=lambda k: (k not in critical_keys, averages[k], -_WEIGHT.get(k, 1)),
    )[:MAX_FOCUS]
    strong = sorted(
        (k for k, v in averages.items() if v >= STRONG and k not in weak),
        key=lambda k: (-averages[k], -_WEIGHT.get(k, 1)),
    )
    timed = [c for c in cards if c.processing_s is not None]
    progress = []
    if previous is not None:
        for k in previous.focus:
            if k in previous.criteria and k in averages:
                progress.append(Progress(k, TITLES.get(k, k), previous.criteria[k], averages[k]))
    return FeedbackFacts(
        session_title=title,
        threshold=threshold,
        cards=len(cards),
        assessed=len(assessed),
        avg_score=round(sum(c.score for c in assessed if c.score is not None) / len(assessed), 1) if assessed else None,
        passed=sum(1 for c in assessed if c.passed),
        timed=len(timed),
        in_norm=sum(1 for c in timed if c.processing_s is not None and c.processing_s <= c.norm_s),
        norm_s=timed[0].norm_s if timed else None,
        criteria=averages,
        strengths=[(k, averages[k]) for k in strong[:MAX_STRENGTHS]],
        focus=[_focus(k, averages[k], assessed) for k in weak],
        progress=progress,
        expert_comments=[(c.number, c.expert_comment) for c in cards if c.expert_comment],
    )


def _progress_line(p: Progress) -> str:
    delta = p.now - p.before
    verdict = "есть прогресс" if delta >= 0.1 else "пока хуже, чем было" if delta <= -0.1 else "без заметных изменений"
    return f"{p.title}: было {pct(p.before)}, стало {pct(p.now)} — {verdict}."


def rules_draft(f: FeedbackFacts) -> DraftParts:
    """Черновик без модели — из тех же фактов, что получает модель (изолированный контур, ошибка модели)."""
    if not f.cards:
        return DraftParts(
            summary=f"В занятии «{f.session_title}» у вас нет сохранённых карточек — оценивать пока нечего."
        )
    if not f.assessed:
        return DraftParts(summary=f"Занятие «{f.session_title}»: {f.cards} {cards_word(f.cards)}, оценок пока нет.")
    summary = (
        f"Занятие «{f.session_title}»: {f.cards} {cards_word(f.cards)}, средний балл {_num(f.avg_score or 0)} "
        f"при пороге {_num(f.threshold)}, зачтено {f.passed} из {f.assessed}."
    )
    if f.timed and f.norm_s is not None:
        summary += f" В норматив {_num(f.norm_s)} с уложились {f.in_norm} из {f.timed}."
    improve = []
    for x in f.focus:
        head = f"{x.title} — {pct(x.average)}"
        if x.critical:
            head += ", критическая ошибка: такая карточка не зачитывается при любом балле"
        detail = f": {x.example}, {_numbers(x.cards)}" if x.example and x.cards else ""
        improve.append(f"{head}{detail}. {x.advice}".strip())
    high = (f.avg_score or 0) >= f.threshold + 15
    serious = [x for x in f.focus if x.critical or x.average < STRONG]
    if serious:
        next_step = f"на следующем занятии сосредоточьтесь на одном — «{serious[0].title}»."
    elif f.focus and high:
        next_step = f"уберите мелкие неточности («{f.focus[0].title}») — и можно переходить к сценариям сложнее."
    elif high:
        next_step = "можно переходить к сценариям сложнее."
    else:
        next_step = "закрепите результат на сценариях того же уровня."
    return DraftParts(
        summary=summary,
        progress=[_progress_line(p) for p in f.progress],
        strengths=[f"{STRENGTHS.get(k, TITLES.get(k, k))} — {pct(v)}." for k, v in f.strengths],
        improve=improve,
        next_step=next_step,
    )


def _bullet(s: str) -> str:
    return "— " + s.strip().lstrip("-–—•* ").strip()


def compose(p: DraftParts) -> str:
    """Текст отзыва: итог, «С прошлого отзыва», «Что получилось», «Что подтянуть», «Следующий шаг»."""
    blocks = [p.summary.strip()]
    for heading, items in (
        ("С прошлого отзыва:", p.progress),
        ("Что получилось:", p.strengths),
        ("Что подтянуть:", p.improve),
    ):
        items = [i for i in items if i.strip()]
        if items:
            blocks.append("\n".join([heading, *(_bullet(i) for i in items)]))
    step = p.next_step.strip()
    if step:
        blocks.append(f"Следующий шаг: {step[0].lower()}{step[1:]}" if step[:1].isupper() else f"Следующий шаг: {step}")
    return "\n\n".join(b for b in blocks if b)[:MAX_TEXT]


def similarity(draft: str, final: str) -> float:
    """Насколько сохранённый отзыв совпадает с черновиком, 0–1: сколько преподаватель правит черновики (п. 3.5)."""
    return round(SequenceMatcher(None, draft.strip(), final.strip()).ratio(), 2)
