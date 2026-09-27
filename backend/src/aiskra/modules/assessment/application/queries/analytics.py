"""Продвинутая аналитика преподавателя (specs/4.5-teacher-analytics.md; основания —
docs/research/Подготовка_персонала_112_и_ЕДДС.md):

- профиль обучающегося по всем занятиям преподавателя (ПС 12.002 C/03, C/04);
- «норматив / факт» по времени (ПП РФ № 1931; форма 1/112, приказ МЧС № 192);
- разбор занятия — характерные недостатки группы (ГОСТ Р 22.7.01, п. 3.12.3);
- подбор задания по слабым местам (ПС 12.002 C/05);
- готовность к допуску по шкале Программы подготовки ЕДДС 2023 (ПС 12.002 C/03, specs/4.6).

Всё строится по фактам занятий и сохранённым оценкам; видны только занятия самого преподавателя.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from aiskra.modules.assessment.application.ports.attempts import AssessmentRepository
from aiskra.modules.assessment.application.ports.reports import ScenarioBank, SessionFacts, SessionFactsSource
from aiskra.modules.assessment.application.queries.reports import cards_of
from aiskra.modules.assessment.domain.analytics import NormStat, error_key, next_difficulty, norm_stat
from aiskra.modules.assessment.domain.readiness import MIN_CARDS, Readiness, assess_readiness
from aiskra.modules.assessment.domain.recommendations import RECOMMENDATIONS, recommend
from aiskra.modules.assessment.domain.scoring import CARD_NORM_SECONDS, DDS_NORM_SECONDS, PASS_THRESHOLD, TITLES
from aiskra.shared.application import Query
from aiskra.shared.errors import NotFoundError
from aiskra.shared.security import Principal


@dataclass(frozen=True)
class Attempt:
    """Одна попытка обучающегося: карточка 112 оператора или работа ДДС по карточке."""

    session_id: UUID
    session_title: str
    session_at: datetime | None
    student_id: UUID
    full_name: str
    role: str
    service_code: str | None
    card_number: int
    at: datetime | None
    time_s: float | None  # 112 — заполнение карточки, ДДС — решение по карточке
    norm_s: float
    incident_group: int | None
    difficulty: int | None
    score: float | None = None
    passed: bool | None = None
    criteria: dict[str, float | None] = field(default_factory=dict)
    errors: list[tuple[str, str]] = field(default_factory=list)  # (ключ критерия, текст замечания)
    expert: bool = False  # балл поставил преподаватель


def attempts_of(facts: SessionFacts, records: dict[tuple[UUID, str, str | None], Any]) -> list[Attempt]:
    norm112 = float(facts.settings.get("norm_112", CARD_NORM_SECONDS))
    norm_dds = float(facts.settings.get("norm_dds", DDS_NORM_SECONDS))
    out = []
    for p in facts.participants:
        for card in cards_of(p, facts.cards):
            service = p.service_code if p.role == "dds" else None
            rec = records.get((card.card_id, p.role, service))
            out.append(
                Attempt(
                    session_id=facts.session_id,
                    session_title=facts.title,
                    session_at=facts.started_at,
                    student_id=p.student_id,
                    full_name=p.full_name,
                    role=p.role,
                    service_code=p.service_code,
                    card_number=card.number,
                    at=card.saved_at,
                    time_s=card.processing_s if p.role == "112" else card.reactions.get(p.service_code or ""),
                    norm_s=norm112 if p.role == "112" else norm_dds,
                    incident_group=card.incident_group,
                    difficulty=card.difficulty,
                    score=rec.score if rec else None,
                    passed=rec.passed if rec else None,
                    criteria={c["key"]: c.get("score") for c in rec.details.get("criteria", [])} if rec else {},
                    errors=[(c["key"], e) for c in rec.details.get("criteria", []) for e in c.get("errors", [])]
                    if rec
                    else [],
                    expert=bool(rec and rec.details.get("expert")),
                )
            )
    return out


class TeacherAttempts:
    """Попытки обучающихся во всех начатых занятиях преподавателя (или в одном занятии)."""

    def __init__(self, source: SessionFactsSource, repo: AssessmentRepository) -> None:
        self._source = source
        self._repo = repo

    async def facts(self, teacher: UUID, session_id: UUID) -> SessionFacts:
        facts = await self._source.session(session_id)
        if facts is None or facts.teacher_id != teacher:
            raise NotFoundError("Занятие не найдено", code="session_not_found")
        return facts

    async def of_session(self, facts: SessionFacts) -> list[Attempt]:
        records: dict[tuple[UUID, str, str | None], Any] = {}
        for p in facts.participants:
            for card in cards_of(p, facts.cards):
                service = p.service_code if p.role == "dds" else None
                rec = await self._repo.latest(card.card_id, p.role, service)
                if rec:
                    records[(card.card_id, p.role, service)] = rec
        return attempts_of(facts, records)

    async def all(self, teacher: UUID, since: datetime | None = None) -> list[Attempt]:
        out: list[Attempt] = []
        for sid in await self._source.teacher_sessions(teacher, since):
            facts = await self._source.session(sid)
            if facts is not None:
                out += await self.of_session(facts)
        return sorted(out, key=lambda a: a.at or datetime.min.replace(tzinfo=UTC))


def _avg(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 1) if xs else None


def _criteria_avg(attempts: list[Attempt]) -> dict[str, float]:
    per: dict[str, list[float]] = defaultdict(list)
    for a in attempts:
        for k, v in a.criteria.items():
            if v is not None:
                per[k].append(float(v))
    return {k: sum(v) / len(v) for k, v in per.items()}


def _samples(attempts: list[Attempt], role: str) -> list[tuple[float, float]]:
    return [(a.time_s, a.norm_s) for a in attempts if a.role == role and a.time_s is not None]


def _frequent_errors(attempts: list[Attempt], limit: int = 8) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    cards: dict[str, list[int]] = defaultdict(list)
    who: dict[str, set[str]] = defaultdict(set)
    for a in attempts:
        for key, text in a.errors:
            k = error_key(TITLES.get(key, key), text)
            counter[k] += 1
            if a.card_number not in cards[k]:
                cards[k].append(a.card_number)
            who[k].add(a.full_name)
    return [
        {"text": t, "count": n, "cards": cards[t][:5], "students": sorted(who[t])}
        for t, n in counter.most_common(limit)
    ]


def _by_group(attempts: list[Attempt], titles: dict[int, str]) -> list[dict[str, Any]]:
    per: dict[int, list[Attempt]] = defaultdict(list)
    for a in attempts:
        if a.incident_group is not None:
            per[a.incident_group].append(a)
    rows = []
    for gid, xs in per.items():
        scores = [a.score for a in xs if a.score is not None]
        rows.append(
            {
                "group_id": gid,
                "title": titles.get(gid, str(gid)),
                "cards": len(xs),
                "avg_score": _avg(scores),
                "errors": sum(len(a.errors) for a in xs),
            }
        )
    return sorted(rows, key=lambda r: (r["avg_score"] is None, r["avg_score"] or 0))


# ------------------------------------------------------------------ «норматив / факт»


@dataclass(frozen=True, kw_only=True)
class NormReport(Query):
    actor: Principal
    days: int | None = 30
    session_id: UUID | None = None


@dataclass(frozen=True)
class NormRow:
    key: str  # обучающийся или занятие
    title: str
    role: str
    stat: NormStat


@dataclass(frozen=True)
class NormReportView:
    period: str
    card_112: NormStat
    dds: NormStat
    by_student: list[NormRow]
    by_session: list[dict[str, Any]]  # [{session_id, title, at, card_112, dds}]
    source: str = "ПП РФ № 1931, п. 9 «р»; форма 1/112 (приказ МЧС России № 192)"


class NormReportHandler:
    def __init__(self, source: SessionFactsSource, repo: AssessmentRepository) -> None:
        self._attempts = TeacherAttempts(source, repo)

    async def __call__(self, q: NormReport) -> NormReportView:
        if q.session_id:
            facts = await self._attempts.facts(q.actor.user_id, q.session_id)
            attempts, period = await self._attempts.of_session(facts), f"занятие «{facts.title}»"
        else:
            since = datetime.now(UTC) - timedelta(days=q.days) if q.days else None
            attempts = await self._attempts.all(q.actor.user_id, since)
            period = f"последние {q.days} дн." if q.days else "все занятия"
        rows = []
        for (sid, role), xs in _group_by(attempts, lambda a: (a.student_id, a.role)).items():
            stat = norm_stat(_samples(xs, role))
            if stat.count:
                label = xs[0].full_name + ("" if role == "112" else f" · ДДС {xs[0].service_code}")
                rows.append(NormRow(key=str(sid), title=label, role=role, stat=stat))
        rows.sort(key=lambda r: (r.role, r.stat.within_share if r.stat.within_share is not None else 2))
        sessions: list[dict[str, Any]] = [
            {
                "session_id": str(sid),
                "title": xs[0].session_title,
                "at": xs[0].session_at.isoformat() if xs[0].session_at else None,
                "card_112": norm_stat(_samples(xs, "112")),
                "dds": norm_stat(_samples(xs, "dds")),
            }
            for sid, xs in _group_by(attempts, lambda a: a.session_id).items()
        ]
        sessions.sort(key=lambda s: s["at"] or "", reverse=True)
        return NormReportView(
            period=period,
            card_112=norm_stat(_samples(attempts, "112")),
            dds=norm_stat(_samples(attempts, "dds")),
            by_student=rows,
            by_session=sessions,
        )


def _group_by(attempts: list[Attempt], key: Any) -> dict[Any, list[Attempt]]:
    out: dict[Any, list[Attempt]] = defaultdict(list)
    for a in attempts:
        out[key(a)].append(a)
    return out


# ------------------------------------------------------------------ готовность к допуску (specs/4.6)

READINESS_LAST = 10  # оценку ставим по последним карточкам: ранние попытки не тянут вниз


@dataclass(frozen=True)
class ReadinessRow:
    student_id: UUID
    full_name: str
    role: str
    service_code: str | None
    sessions: int
    groups: int  # отработано групп классификатора
    last_at: datetime | None
    expert: int  # сколько из учтённых карточек с экспертной оценкой
    readiness: Readiness


def readiness_rows(
    attempts: list[Attempt], last: int = READINESS_LAST, min_cards: int = MIN_CARDS
) -> list[ReadinessRow]:
    """Готовность по каждой роли обучающегося: последние `last` оценённых карточек, их балл и время."""
    rows = []
    for (sid, role), xs in _group_by(attempts, lambda a: (a.student_id, a.role)).items():
        assessed = [a for a in xs if a.score is not None][-last:]
        r = assess_readiness(
            [a.score for a in assessed if a.score is not None],
            [(a.time_s, a.norm_s) for a in assessed if a.time_s is not None],
            min_cards=min_cards,
        )
        rows.append(
            ReadinessRow(
                student_id=sid,
                full_name=xs[0].full_name,
                role=role,
                service_code=xs[0].service_code if role == "dds" else None,
                sessions=len({a.session_id for a in xs}),
                groups=len({a.incident_group for a in xs if a.incident_group is not None}),
                last_at=xs[-1].at,
                expert=sum(1 for a in assessed if a.expert),
                readiness=r,
            )
        )
    return sorted(rows, key=lambda r: (r.role, -(r.readiness.grade or 0), r.full_name))


@dataclass(frozen=True, kw_only=True)
class ReadinessQuery(Query):
    actor: Principal
    student_ids: list[UUID] = field(default_factory=list)  # пусто — все обучающиеся занятий преподавателя
    last: int = READINESS_LAST
    min_cards: int = MIN_CARDS


@dataclass(frozen=True)
class ReadinessView:
    rows: list[ReadinessRow]
    last: int
    min_cards: int
    generated_at: datetime
    teacher: str
    scale: list[dict[str, str]]
    source: str = (
        "Шкала итогового контроля — Программа подготовки дежурно-диспетчерского персонала ЕДДС (МЧС России, "
        "протокол Правкомиссии от 31.10.2023 № 9); нормативы времени — ПП РФ № 1931; оценка готовности — "
        "профстандарт 12.002, функция C/03"
    )


SCALE = [
    {"grade": "отлично", "rule": "средний балл 90–100 %, в нормативе не меньше 90 % карточек"},
    {"grade": "хорошо", "rule": "75–90 %, в нормативе не меньше 90 % карточек"},
    {
        "grade": "удовлетворительно",
        "rule": "60–75 % или небольшое превышение времени (≥ 60 % в нормативе, 90-й процентиль ≤ 1,5 норматива)",
    },
    {"grade": "неудовлетворительно", "rule": "меньше 60 % или значительное превышение времени"},
]


class ReadinessHandler:
    def __init__(self, source: SessionFactsSource, repo: AssessmentRepository) -> None:
        self._attempts = TeacherAttempts(source, repo)

    async def __call__(self, q: ReadinessQuery) -> ReadinessView:
        attempts = await self._attempts.all(q.actor.user_id)
        if q.student_ids:
            wanted = set(q.student_ids)
            attempts = [a for a in attempts if a.student_id in wanted]
        return ReadinessView(
            rows=readiness_rows(attempts, q.last, q.min_cards),
            last=q.last,
            min_cards=q.min_cards,
            generated_at=datetime.now(UTC),
            teacher=q.actor.full_name,
            scale=SCALE,
        )


# ------------------------------------------------------------------ профиль обучающегося


@dataclass(frozen=True, kw_only=True)
class StudentProfile(Query):
    actor: Principal
    student_id: UUID


@dataclass(frozen=True)
class StudentProfileView:
    student_id: UUID
    full_name: str
    roles: list[str]
    sessions: int
    cards: int
    avg_score: float | None
    passed_share: float | None
    points: list[dict[str, Any]]  # [{t, v, role, card_number, session, passed}]
    criteria: list[dict[str, Any]]  # [{key, title, role, student, group, delta}]
    frequent_errors: list[dict[str, Any]]
    coverage: list[dict[str, Any]]  # группы классификатора: отработано, балл, ошибки
    not_practiced: list[dict[str, Any]]  # группы с утверждёнными сценариями, которых ещё не было
    by_difficulty: list[dict[str, Any]]  # [{difficulty, cards, avg_score}]
    card_112: NormStat
    dds: NormStat
    recommendations: list[dict[str, Any]]
    readiness: list[ReadinessRow] = field(default_factory=list)


class StudentProfileHandler:
    def __init__(self, source: SessionFactsSource, repo: AssessmentRepository, bank: ScenarioBank) -> None:
        self._attempts = TeacherAttempts(source, repo)
        self._bank = bank

    async def __call__(self, q: StudentProfile) -> StudentProfileView:
        everyone = await self._attempts.all(q.actor.user_id)
        mine = [a for a in everyone if a.student_id == q.student_id]
        if not mine:
            raise NotFoundError("У обучающегося нет карточек в ваших занятиях", code="student_not_found")
        roles = sorted({a.role for a in mine})
        own, group = _criteria_avg(mine), _criteria_avg([a for a in everyone if a.role in roles])
        criteria: list[dict[str, Any]] = sorted(
            (
                {
                    "key": k,
                    "title": TITLES.get(k, k),
                    "student": round(v, 2),
                    "group": round(group[k], 2) if k in group else None,
                    "delta": round(v - group[k], 2) if k in group else None,
                }
                for k, v in own.items()
            ),
            key=lambda c: c["student"],
        )
        titles = await self._bank.group_titles()
        coverage = _by_group(mine, titles)
        practiced = {c["group_id"] for c in coverage}
        bank = await self._bank.approved_count([], None)
        scores = [a.score for a in mine if a.score is not None]
        passed = [bool(a.passed) for a in mine if a.passed is not None]
        diffs: dict[int, list[float]] = defaultdict(list)
        for a in mine:
            if a.difficulty is not None and a.score is not None:
                diffs[a.difficulty].append(a.score)
        return StudentProfileView(
            student_id=q.student_id,
            full_name=mine[0].full_name,
            roles=roles,
            sessions=len({a.session_id for a in mine}),
            cards=len(mine),
            avg_score=_avg(scores),
            passed_share=round(sum(passed) / len(passed), 3) if passed else None,
            points=[
                {
                    "t": a.at.isoformat() if a.at else "",
                    "v": a.score,
                    "role": a.role,
                    "card_number": a.card_number,
                    "session": a.session_title,
                    "passed": a.passed,
                }
                for a in mine
                if a.score is not None
            ],
            criteria=criteria,
            frequent_errors=_frequent_errors(mine),
            coverage=coverage,
            not_practiced=[
                {"group_id": gid, "title": titles.get(gid, str(gid)), "approved": n}
                for gid, n in sorted(bank.items())
                if gid not in practiced and n
            ],
            by_difficulty=[{"difficulty": d, "cards": len(v), "avg_score": _avg(v)} for d, v in sorted(diffs.items())],
            card_112=norm_stat(_samples(mine, "112")),
            dds=norm_stat(_samples(mine, "dds")),
            recommendations=recommend(own),
            readiness=readiness_rows(mine),
        )


# ------------------------------------------------------------------ разбор занятия


@dataclass(frozen=True, kw_only=True)
class SessionDebrief(Query):
    actor: Principal
    session_id: UUID


@dataclass(frozen=True)
class DebriefView:
    session_id: UUID
    title: str
    started_at: datetime | None
    cards: int
    assessed: int
    avg_score: float | None
    passed_share: float | None
    top_errors: list[dict[str, Any]]  # [{text, count, cards, students}]
    weak_criteria: list[dict[str, Any]]  # [{key, title, average, advice}]
    weak_groups: list[dict[str, Any]]  # группы классификатора ниже порога — что повторить
    overdue: list[dict[str, Any]]  # карточки сверх норматива [{who, role, card_number, time_s, norm_s}]
    best: list[dict[str, Any]]  # лучшие результаты [{who, role, avg_score}]
    card_112: NormStat
    dds: NormStat


class SessionDebriefHandler:
    def __init__(self, source: SessionFactsSource, repo: AssessmentRepository, bank: ScenarioBank) -> None:
        self._attempts = TeacherAttempts(source, repo)
        self._bank = bank

    async def __call__(self, q: SessionDebrief) -> DebriefView:
        facts = await self._attempts.facts(q.actor.user_id, q.session_id)
        attempts = await self._attempts.of_session(facts)
        threshold = float(facts.settings.get("threshold", PASS_THRESHOLD))
        assessed = [a for a in attempts if a.score is not None]
        weak = sorted(_criteria_avg(assessed).items(), key=lambda kv: kv[1])[:3]
        titles = await self._bank.group_titles()
        per_student = _group_by(assessed, lambda a: (a.full_name, a.role))
        best = sorted(
            (
                {"who": who, "role": role, "avg_score": _avg([x.score for x in xs if x.score is not None])}
                for (who, role), xs in per_student.items()
            ),
            key=lambda b: -(b["avg_score"] or 0),
        )[:3]
        overdue: list[dict[str, Any]] = [
            {
                "who": a.full_name,
                "role": a.role,
                "card_number": a.card_number,
                "time_s": round(a.time_s, 1),
                "norm_s": a.norm_s,
            }
            for a in attempts
            if a.time_s is not None and a.time_s > a.norm_s
        ]
        overdue.sort(key=lambda o: -(o["time_s"] - o["norm_s"]))
        return DebriefView(
            session_id=facts.session_id,
            title=facts.title,
            started_at=facts.started_at,
            cards=len(attempts),
            assessed=len(assessed),
            avg_score=_avg([a.score for a in assessed if a.score is not None]),
            passed_share=round(sum(bool(a.passed) for a in assessed) / len(assessed), 3) if assessed else None,
            top_errors=_frequent_errors(assessed, limit=5),
            weak_criteria=[
                {"key": k, "title": TITLES.get(k, k), "average": round(v, 2), "advice": RECOMMENDATIONS.get(k, "")}
                for k, v in weak
                if v < 0.85
            ],
            weak_groups=[
                g for g in _by_group(assessed, titles) if g["avg_score"] is not None and g["avg_score"] < threshold
            ],
            overdue=overdue[:8],
            best=best,
            card_112=norm_stat(_samples(attempts, "112")),
            dds=norm_stat(_samples(attempts, "dds")),
        )


# ------------------------------------------------------------------ задание по слабым местам


@dataclass(frozen=True, kw_only=True)
class SuggestAssignment(Query):
    actor: Principal
    student_ids: list[UUID]


@dataclass(frozen=True)
class AssignmentSuggestion:
    title: str
    mode: str  # cards_112 | dds_actions | mixed
    groups: list[dict[str, Any]]  # [{group_id, title, reason, avg_score, approved}]
    difficulty: int
    difficulty_reason: str
    focus: list[dict[str, Any]]  # слабые критерии с советом — что сказать на инструктаже
    participants: list[dict[str, Any]]  # [{student_id, full_name, role, service_code}]
    approved_total: int  # утверждённых сценариев выбранных групп и сложности
    warnings: list[str]


class SuggestAssignmentHandler:
    """Подбор занятия: группы классификатора, где у выбранных обучающихся больше всего ошибок, плюс ещё не
    отработанные; сложность — по динамике балла; фокус инструктажа — слабые критерии."""

    MAX_GROUPS = 3

    def __init__(self, source: SessionFactsSource, repo: AssessmentRepository, bank: ScenarioBank) -> None:
        self._attempts = TeacherAttempts(source, repo)
        self._bank = bank

    async def __call__(self, q: SuggestAssignment) -> AssignmentSuggestion:
        wanted = set(q.student_ids)
        mine = [a for a in await self._attempts.all(q.actor.user_id) if a.student_id in wanted]
        titles = await self._bank.group_titles()
        bank = await self._bank.approved_count([], None)
        warnings: list[str] = []
        assessed = [a for a in mine if a.score is not None]
        if not assessed:
            warnings.append("у выбранных обучающихся нет оценённых карточек — подбор по непройденным группам")
        coverage = _by_group(assessed, titles)
        picked = [
            {
                "group_id": g["group_id"],
                "title": g["title"],
                "avg_score": g["avg_score"],
                "reason": f"средний балл {g['avg_score']:.0f}, замечаний {g['errors']}",
                "approved": bank.get(g["group_id"], 0),
            }
            for g in coverage
            if g["avg_score"] is not None and g["avg_score"] < PASS_THRESHOLD + 15
        ][: self.MAX_GROUPS]
        practiced = {g["group_id"] for g in coverage}
        for gid, n in sorted(bank.items(), key=lambda kv: -kv[1]):
            if len(picked) >= self.MAX_GROUPS:
                break
            if gid not in practiced and n:
                picked.append(
                    {
                        "group_id": gid,
                        "title": titles.get(gid, str(gid)),
                        "avg_score": None,
                        "reason": "ещё не отрабатывалась",
                        "approved": n,
                    }
                )
        if not picked and coverage:  # слабых и новых групп нет — закрепление самой слабой из пройденных
            g = coverage[0]
            picked.append(
                {
                    "group_id": g["group_id"],
                    "title": g["title"],
                    "avg_score": g["avg_score"],
                    "reason": f"закрепление: средний балл {g['avg_score']:.0f} — ниже, чем по остальным группам"
                    if g["avg_score"] is not None
                    else "закрепление",
                    "approved": bank.get(g["group_id"], 0),
                }
            )
        recent = [a.score for a in assessed[-10:] if a.score is not None]
        difficulty, reason = next_difficulty([a.difficulty for a in mine if a.difficulty], recent, PASS_THRESHOLD)
        for g in picked:
            if not g["approved"]:
                warnings.append(f"в банке нет утверждённых сценариев группы «{g['title']}» — сгенерируйте их")
        at_level = await self._bank.approved_count([g["group_id"] for g in picked], difficulty) if picked else {}
        total = sum(at_level.values())
        if picked and not total:
            warnings.append(
                f"сценариев сложности {difficulty} в этих группах нет — будут выданы ближайшие по сложности"
            )
        last: dict[UUID, Attempt] = {a.student_id: a for a in mine}
        participants = [
            {
                "student_id": str(sid),
                "full_name": a.full_name,
                "role": a.role,
                "service_code": a.service_code if a.role == "dds" else None,
            }
            for sid, a in last.items()
        ]
        roles = {p["role"] for p in participants}
        mode = "mixed" if roles == {"112", "dds"} else "dds_actions" if roles == {"dds"} else "cards_112"
        focus: list[dict[str, Any]] = []
        for r in recommend(_criteria_avg(assessed), limit=3):
            k = str(r["key"])
            focus.append({"key": k, "title": TITLES.get(k, k), "average": r["average"], "advice": r["text"]})
        names = [p["full_name"] for p in participants]
        who = names[0] if len(names) == 1 else f"{len(names)} обуч." if names else "группа"
        topic = ", ".join(g["title"] for g in picked[:2]) or "повторение"
        return AssignmentSuggestion(
            title=f"Работа над ошибками: {topic} — {who}"[:120],
            mode=mode,
            groups=picked,
            difficulty=difficulty,
            difficulty_reason=reason,
            focus=focus,
            participants=participants,
            approved_total=total,
            warnings=warnings,
        )
