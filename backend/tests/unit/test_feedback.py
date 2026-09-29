"""П. 4.7: черновик отзыва преподавателя.

Правила: итог → что получилось → что подтянуть (до трёх, критические первыми) → следующий шаг; сравнение с прошлым
отзывом. Модель: берётся её текст, в модель — без ФИО; ошибка модели — черновик по правилам."""

import asyncio
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel

from aiskra.ai.adapters.fake import FakeLLM
from aiskra.ai.ports import ChatMessage, LLMParams, LLMResult
from aiskra.ai.router import ModelRouter, TaskProfile
from aiskra.ai.tasks import AITask
from aiskra.modules.assessment.application.ports.attempts import AssessmentRecord
from aiskra.modules.assessment.application.ports.feedback import FeedbackRecord
from aiskra.modules.assessment.application.ports.reports import ReportCard, ReportParticipant, SessionFacts
from aiskra.modules.assessment.application.queries.feedback import DraftFeedback, DraftFeedbackHandler, redact
from aiskra.modules.assessment.domain.feedback import (
    MAX_FOCUS,
    CardFacts,
    PreviousFeedback,
    cards_word,
    compose,
    rules_draft,
    similarity,
    summarize,
)
from aiskra.shared.errors import ExternalServiceError
from aiskra.shared.security import Principal, Role


def card(
    number: int, score: float, criteria: dict[str, float | None], errors: tuple[str, ...] | list[str] = (), **kw: object
) -> CardFacts:
    return CardFacts(
        number=number,
        score=score,
        passed=score >= 70,
        processing_s=kw.pop("processing_s", 60.0),  # type: ignore[arg-type]
        norm_s=75,
        errors=list(errors),
        criteria=criteria,
        **kw,  # type: ignore[arg-type]
    )


CARDS = [
    card(
        3,
        62,
        {"type": 1.0, "services": 1.0, "address": 0.5, "victims": 0.0, "grammar": None},
        ["Адрес: номер дома не совпадает (эталон 37)", "Пострадавшие: не указано число пострадавших"],
    ),
    card(
        5,
        81,
        {"type": 1.0, "services": 0.9, "address": 0.6, "victims": 1.0},
        ["Адрес: номер дома не совпадает (эталон 7)"],
        processing_s=90.0,
    ),
]


def test_summary_counts_strengths_focus() -> None:
    f = summarize("Пожары", 70, CARDS)
    assert (f.cards, f.assessed, f.avg_score, f.passed) == (2, 2, 71.5, 1)
    assert (f.timed, f.in_norm, f.norm_s) == (2, 1, 75)
    assert [k for k, _ in f.strengths] == ["type"]  # «Службы» 95 % — с замечанием, значит в «подтянуть»
    assert "grammar" not in f.criteria  # не проверялся — не сильная и не слабая сторона
    address = next(x for x in f.focus if x.key == "address")
    assert address.example == "номер дома не совпадает (эталон 37)" and address.cards == [3, 5]
    assert address.advice.startswith("Выбирайте адрес")
    assert [x.key for x in f.focus] == ["victims", "address", "services"]  # от худшего, включая мелкие потери


def test_critical_first_and_focus_limited() -> None:
    crit = card(
        7,
        60,
        {"type": 1.0, "services": 0.95, "address": 0.3, "flags": 0.4, "victims": 0.5, "applicant": 0.6},
        ["Службы: не направлена служба 01"],
        critical=["Службы"],
    )
    f = summarize("Смена", 70, [crit])
    assert f.focus[0].key == "services" and f.focus[0].critical  # 95 %, но критическая — первой
    assert len(f.focus) == MAX_FOCUS
    text = compose(rules_draft(f))
    assert "критическая ошибка" in text and "не направлена служба 01, карточка № 7" in text


def test_rules_draft_structure() -> None:
    text = compose(rules_draft(summarize("Пожары", 70, CARDS)))
    assert text.startswith("Занятие «Пожары»: 2 карточки, средний балл 71,5 при пороге 70, зачтено 1 из 2.")
    assert "В норматив 75 с уложились 1 из 2." in text
    blocks = text.split("\n\n")
    assert [b.split("\n")[0] for b in blocks[1:]] == ["Что получилось:", "Что подтянуть:", blocks[-1].split("\n")[0]]
    assert "Что получилось:\n— Тип происшествия выбираете верно — 100 %.\n\nЧто подтянуть:" in text
    assert blocks[-1] == "Следующий шаг: на следующем занятии сосредоточьтесь на одном — «Пострадавшие»."
    assert "Петров" not in text and "группа" not in text.lower()  # без сравнения с другими обучающимися


def test_progress_against_previous_feedback() -> None:
    prev = PreviousFeedback(
        "Прошлое занятие", focus=["address", "victims", "flags"], criteria={"address": 0.3, "victims": 0.5}
    )
    f = summarize("Пожары", 70, CARDS, prev)
    assert [(p.key, p.before, p.now) for p in f.progress] == [("address", 0.3, 0.55), ("victims", 0.5, 0.5)]
    text = compose(rules_draft(f))
    assert "С прошлого отзыва:\n— Адрес: было 30 %, стало 55 % — есть прогресс." in text
    assert "— Пострадавшие: было 50 %, стало 50 % — без заметных изменений." in text


def test_no_cards_and_not_assessed() -> None:
    assert (
        compose(rules_draft(summarize("Пусто", 70, [])))
        == "В занятии «Пусто» у вас нет сохранённых карточек — оценивать пока нечего."
    )
    raw = CardFacts(number=1, score=None, passed=None, processing_s=None, norm_s=75, errors=[], criteria={})
    assert compose(rules_draft(summarize("Смена", 70, [raw]))) == "Занятие «Смена»: 1 карточка, оценок пока нет."


def test_high_score_still_names_slips() -> None:
    good = [
        card(1, 95, {"type": 1.0, "services": 1.0}),
        card(2, 90, {"type": 1.0, "services": 0.9}, ["Службы: лишняя 04"]),
    ]
    parts = rules_draft(summarize("Смена", 70, good))
    assert parts.improve == [
        "Службы — 95 %: лишняя 04, карточка № 2. Сверяйтесь с автоподбором служб: главная служба — первой; "
        "не удаляйте службы, подобранные по адресу."
    ]
    assert parts.next_step == "уберите мелкие неточности («Службы») — и можно переходить к сценариям сложнее."
    clean = rules_draft(summarize("Смена", 70, [card(1, 100, {"type": 1.0, "services": 1.0})]))
    assert not clean.improve and clean.next_step == "можно переходить к сценариям сложнее."


def test_helpers() -> None:
    assert [cards_word(n) for n in (1, 2, 5, 11, 21, 22, 112)] == [
        "карточка", "карточки", "карточек", "карточек", "карточка", "карточки", "карточек"]  # fmt: skip
    assert similarity("Отзыв", "Отзыв") == 1.0 and similarity("", "совсем другое") == 0.0
    assert redact("Иванов молодец, иванов!", "Иванов Иван") == "[ФИО] молодец, [ФИО]!"


# ------------------------------------------------------------------ обработчик черновика с моделью

TEACHER = Principal(user_id=uuid4(), session_id=uuid4(), login="teacher", full_name="Преподаватель", role=Role.TEACHER)
STUDENT = uuid4()
SESSION = uuid4()


class Source:
    async def session(self, session_id: UUID) -> SessionFacts | None:
        cards = [
            ReportCard(card_id=UUID(int=n), number=n, author_id=STUDENT, origin="operator", status="saved",
                       saved_at=datetime(2026, 9, 29, tzinfo=UTC), processing_s=60, card_types=["101"])
            for n in (3, 5)
        ]  # fmt: skip
        return SessionFacts(
            session_id=SESSION, teacher_id=TEACHER.user_id, title="Работа над ошибками: Иванов Иван", mode="cards_112",
            status="finished", started_at=datetime(2026, 9, 29, 10, tzinfo=UTC), finished_at=None,
            settings={"threshold": 70}, participants=[ReportParticipant(STUDENT, "Иванов Иван", "112", None)],
            cards=cards,
        )  # fmt: skip

    async def teacher_sessions(self, teacher_id: UUID, since: datetime | None = None) -> list[UUID]:
        return [SESSION]


class Repo:
    async def latest(self, card_id: UUID, role: str, service_code: str | None) -> AssessmentRecord | None:
        c = next(x for x in CARDS if x.number == card_id.int)
        details = {
            "criteria": [{"key": k, "score": v} for k, v in c.criteria.items()],
            "errors": c.errors,
            "critical": [],
            "expert": {"comment": "Иванов, адрес — из справочника"} if c.number == 5 else None,
        }
        return AssessmentRecord(uuid4(), card_id, STUDENT, "112", None, c.score or 0, bool(c.passed), "rules", details)


class Store:
    def __init__(self, previous: list[FeedbackRecord] = ()) -> None:  # type: ignore[assignment]
        self.previous = list(previous)

    async def for_student(self, student_id: UUID) -> list[FeedbackRecord]:
        return self.previous


def handler(llm: FakeLLM, store: Store | None = None) -> DraftFeedbackHandler:
    router = ModelRouter(
        profiles={AITask.FEEDBACK_DRAFT: TaskProfile(task=AITask.FEEDBACK_DRAFT, provider=llm.provider_name)},
        clients={llm.provider_name: llm},
        default_provider=llm.provider_name,
    )
    return DraftFeedbackHandler(Source(), Repo(), store or Store(), router)  # type: ignore[arg-type]


QUERY = DraftFeedback(actor=TEACHER, session_id=SESSION, student_id=STUDENT)


def test_draft_from_model_without_names() -> None:
    answer = {
        "summary": "Две карточки, средний балл 71,5 — на пороге.",
        "strengths": ["- Тип происшествия — без ошибок."],
        "improve": ["Адрес: номер дома из справочника.", "Пострадавшие: спрашивайте всегда.", "третий", "четвёртый"],
        "next_step": "Повторите опрос о пострадавших.",
    }
    llm = FakeLLM(name="demo", model="demo-model", fixtures={AITask.FEEDBACK_DRAFT: answer})
    d = asyncio.run(handler(llm)(QUERY))
    assert d.source == "ai" and d.model == "demo-model" and not d.warnings
    assert d.text.startswith("Две карточки") and "— Тип происшествия — без ошибок." in d.text
    assert d.text.count("\n— ") == 4  # «подтянуть» обрезано до трёх
    assert d.text.endswith("Следующий шаг: повторите опрос о пострадавших.")
    sent = json.loads(llm.calls[0][0][1].content)
    assert "Иванов" not in json.dumps(sent, ensure_ascii=False)  # ни ФИО, ни названия занятия с ФИО
    assert sent["комментарии_преподавателя"] == [{"карточка": 5, "текст": "[ФИО], адрес — из справочника"}]
    assert [x["критерий"] for x in sent["подтянуть"]] == ["Пострадавшие", "Адрес", "Службы"]
    assert [x["key"] for x in d.focus] == ["victims", "address", "services"]


class Broken(FakeLLM):
    async def complete(
        self, messages: list[ChatMessage], *, params: LLMParams, schema: type[BaseModel] | None = None
    ) -> LLMResult:
        raise ExternalServiceError("нет связи", code="llm_unavailable")


def test_model_error_falls_back_to_rules() -> None:
    d = asyncio.run(handler(Broken(name="demo"))(QUERY))
    assert (
        d.source == "rules"
        and d.model is None
        and d.warnings == ["Модель не ответила — черновик составлен по правилам."]
    )
    assert d.text.startswith("Занятие «Работа над ошибками: Иванов Иван»: 2 карточки")


def test_offline_rules_and_previous_feedback() -> None:
    prev = FeedbackRecord(
        session_id=uuid4(), student_id=STUDENT, teacher_id=TEACHER.user_id, session_title="Пожары-1",
        session_started_at=datetime(2026, 9, 28, tzinfo=UTC), text="Подтяните адрес.",
        details={"focus": ["address"], "criteria": {"address": 0.2}},
    )  # fmt: skip
    other = FeedbackRecord(
        session_id=uuid4(), student_id=STUDENT, teacher_id=uuid4(), session_title="Чужое",
        session_started_at=datetime(2026, 9, 28, 12, tzinfo=UTC), text="Другой преподаватель", details={},
    )  # fmt: skip
    llm = FakeLLM()  # fake — модели нет: черновик по правилам без вызова
    d = asyncio.run(handler(llm, Store([other, prev]))(QUERY))
    assert d.source == "rules" and not llm.calls
    assert d.previous is not None and d.previous["session_title"] == "Пожары-1"
    assert "— Адрес: было 20 %, стало 55 % — есть прогресс." in d.text
