"""HTTP-адаптер training: банк сценариев (3.2) и учебные звонки (1.4, 2.3)."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import re
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, Any, Protocol
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from fastapi import Query as QueryParam
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from aiskra.modules.training.api import deps
from aiskra.modules.training.api.schemas import (
    AnswerIn,
    BranchTemplateOut,
    ContactRoleOut,
    CreatedOut,
    CreateSessionIn,
    DdsCallIn,
    EditAnswerIn,
    EditScenarioIn,
    GeneratedOut,
    GenerateIn,
    IncomingIn,
    PhonebookEntryOut,
    PhonebookIn,
    PhonebookOut,
    PsyProfileOut,
    ReplicaIn,
    ReplicaOut,
    ReviewSectionsIn,
    ScenarioPsyIn,
    StatusOut,
)
from aiskra.modules.training.application.commands.calls import (
    AnswerCall,
    AnswerCallHandler,
    CallStarted,
    EndCall,
    EndCallHandler,
    HoldCall,
    HoldCallHandler,
    PauseCall,
    PauseCallHandler,
    Replica,
    SendReplica,
    SendReplicaHandler,
    StartDdsCall,
    StartDdsCallHandler,
    StartIncomingCall,
    StartIncomingCallHandler,
    StreamReplicaFactory,
    TickCall,
    TickCallHandler,
)
from aiskra.modules.training.application.commands.materials import (
    DeleteMaterial,
    DeleteMaterialHandler,
    UpdateMaterial,
    UpdateMaterialHandler,
    UploadMaterial,
    UploadMaterialHandler,
)
from aiskra.modules.training.application.commands.phonebook import SavePhonebook, SavePhonebookHandler
from aiskra.modules.training.application.commands.scenario_review import (
    ReviewSections,
    ReviewSectionsHandler,
    SectionsReviewed,
)
from aiskra.modules.training.application.commands.scenarios import (
    EditAnswer,
    EditAnswerHandler,
    EditScenario,
    EditScenarioHandler,
    GenerateScenarios,
    GenerateScenariosHandler,
    ReviewScenario,
    ReviewScenarioHandler,
    SetScenarioPsy,
    SetScenarioPsyHandler,
)
from aiskra.modules.training.application.commands.self_training import (
    RequestDdsSelfCard,
    RequestDdsSelfCardHandler,
    SelfCardIssued,
)
from aiskra.modules.training.application.commands.sessions import (
    ChangeSessionState,
    ChangeSessionStateHandler,
    CreateSession,
    CreateSessionHandler,
    FeedDdsCard,
    FeedDdsCardHandler,
    FeedResult,
    ParticipantIn,
)
from aiskra.modules.training.application.ports.branching import BranchCatalog
from aiskra.modules.training.application.ports.materials import MaterialRow
from aiskra.modules.training.application.ports.phonebook import Phonebook
from aiskra.modules.training.application.ports.psy import PsyCatalog
from aiskra.modules.training.application.ports.sessions import StudentRow
from aiskra.modules.training.application.psy import TurnSignals
from aiskra.modules.training.application.queries.calls import (
    CallView,
    CardCalls,
    CardCallsHandler,
    GetCall,
    GetCallHandler,
)
from aiskra.modules.training.application.queries.materials import (
    GetMaterial,
    GetMaterialHandler,
    ListMaterials,
    ListMaterialsHandler,
    MaterialView,
)
from aiskra.modules.training.application.queries.phonebook import GetPhonebook, GetPhonebookHandler
from aiskra.modules.training.application.queries.psy_methodology import (
    GetPsyMethodology,
    MethodologyView,
    PsyMethodologyHandler,
)
from aiskra.modules.training.application.queries.scenarios import (
    GetScenario,
    GetScenarioHandler,
    ListScenarios,
    ListScenariosHandler,
    PreviewItem,
    PreviewScenario,
    PreviewScenarioHandler,
    ScenarioPage,
    ScenarioView,
)
from aiskra.modules.training.application.queries.sessions import (
    GetSession,
    GetSessionDefaults,
    GetSessionDefaultsHandler,
    GetSessionHandler,
    ListSessions,
    ListSessionsHandler,
    ListStudents,
    ListStudentsHandler,
    MonitorView,
    MySession,
    MySessionHandler,
    MySessionRow,
    MySessions,
    MySessionsHandler,
    MySessionView,
    SessionMonitor,
    SessionMonitorHandler,
    SessionPage,
    SessionView,
)
from aiskra.modules.training.application.speech import (
    CallRecordingHandler,
    GetCallRecording,
    GetReplicaAudio,
    ReplicaAudioHandler,
    SpeakFragment,
    SpeakFragmentHandler,
    SpeechStatus,
    Transcribe,
    TranscribeHandler,
)
from aiskra.modules.training.application.voice_lab import LabMessage, VoiceLab
from aiskra.modules.training.domain.material import MAX_BYTES, MaterialKind
from aiskra.modules.training.domain.phonebook import MAX_ENTRIES, ROLE_TITLES, PhonebookEntry
from aiskra.modules.training.domain.review import Decision
from aiskra.modules.training.domain.stream_text import RemarkFilter
from aiskra.shared.errors import AppError, DomainError, ExternalServiceError, NotFoundError
from aiskra.shared.security import Permission, Principal
from aiskra.shared.web import CurrentPrincipal, Meta, require

router = APIRouter(prefix="/training", tags=["training"])
Manager = Annotated[Principal, Depends(require(Permission.SCENARIOS_MANAGE))]
Teacher = Annotated[Principal, Depends(require(Permission.LESSONS_CONDUCT))]
Trainee = Annotated[Principal, Depends(require(Permission.TRAINING_PARTICIPATE))]


@router.post(
    "/scenarios/generate", response_model=GeneratedOut, summary="Сгенерировать сценарии (черновики на проверку)"
)
async def generate(
    body: GenerateIn,
    actor: Manager,
    meta: Meta,
    handler: Annotated[GenerateScenariosHandler, Depends(deps.provide_generate)],
) -> GeneratedOut:
    ids = await handler(
        GenerateScenarios(
            actor=actor,
            count=body.count,
            groups=body.groups,
            difficulty=body.difficulty,
            branching=body.branching,
            meta=meta,
        )
    )
    return GeneratedOut(ids=ids)


@router.get(
    "/branch-templates",
    response_model=list[BranchTemplateOut],
    summary="Шаблоны ветвящихся сценариев (F5): ситуация развивается по решениям оператора",
)
async def branch_templates(
    _: Annotated[Principal, Depends(require(Permission.LESSONS_CONDUCT, Permission.SCENARIOS_MANAGE))],
    catalog: Annotated[BranchCatalog, Depends(deps.provide_branch_catalog)],
) -> list[BranchTemplateOut]:
    return [
        BranchTemplateOut(
            id=t.id,
            title=t.title,
            description=t.description,
            incident_codes=list(t.incident_codes),
            forks=len(t.forks),
            outcomes=sorted({n.outcome.code for n in t.terminals if n.outcome}),
        )
        for t in catalog.templates().values()
    ]


@router.get("/scenarios", response_model=ScenarioPage, summary="Банк сценариев")
async def list_scenarios(
    _: Manager,
    handler: Annotated[ListScenariosHandler, Depends(deps.provide_list_scenarios)],
    status: str | None = None,
    difficulty: int | None = None,
    card_type: str | None = None,
    source: str | None = None,
    psy: str | None = QueryParam(default=None, description="any — с профилем, none — без, иначе id профиля (F4)"),
    page: int = 1,
    page_size: int = 30,
) -> ScenarioPage:
    return await handler(
        ListScenarios(
            status=status,
            difficulty=difficulty,
            card_type=card_type,
            source=source,
            psy=psy,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/scenarios/{scenario_id}", response_model=ScenarioView, summary="Сценарий: легенда и эталоны")
async def get_scenario(
    scenario_id: UUID, _: Manager, handler: Annotated[GetScenarioHandler, Depends(deps.provide_get_scenario)]
) -> ScenarioView:
    return await handler(GetScenario(scenario_id=scenario_id))


@router.post("/scenarios/{scenario_id}/approve", response_model=StatusOut, summary="Утвердить сценарий")
async def approve(
    scenario_id: UUID,
    actor: Manager,
    meta: Meta,
    handler: Annotated[ReviewScenarioHandler, Depends(deps.provide_review)],
) -> StatusOut:
    return StatusOut(
        status=await handler(ReviewScenario(actor=actor, scenario_id=scenario_id, approve=True, meta=meta))
    )


@router.post("/scenarios/{scenario_id}/archive", response_model=StatusOut, summary="Сценарий в архив")
async def archive(
    scenario_id: UUID,
    actor: Manager,
    meta: Meta,
    handler: Annotated[ReviewScenarioHandler, Depends(deps.provide_review)],
) -> StatusOut:
    return StatusOut(
        status=await handler(ReviewScenario(actor=actor, scenario_id=scenario_id, approve=False, meta=meta))
    )


@router.post(
    "/scenarios/{scenario_id}/review",
    response_model=SectionsReviewed,
    summary="Частичное утверждение эталона (п. 3.3): разделы «принят» / «на доработку»; все приняты — утверждён",
)
async def review_sections(
    scenario_id: UUID,
    body: ReviewSectionsIn,
    actor: Manager,
    meta: Meta,
    handler: Annotated[ReviewSectionsHandler, Depends(deps.provide_review_sections)],
) -> SectionsReviewed:
    sections = {k: (Decision(v.decision), v.comment) for k, v in body.sections.items()}
    return await handler(ReviewSections(actor=actor, scenario_id=scenario_id, sections=sections, meta=meta))


@router.post("/calls/incoming", response_model=CallStarted, summary="Учебный входящий вызов в 112 (п. 1.4)")
async def incoming(
    body: IncomingIn, actor: Trainee, handler: Annotated[StartIncomingCallHandler, Depends(deps.provide_incoming)]
) -> CallStarted:
    return await handler(StartIncomingCall(actor=actor, groups=body.groups, difficulty=body.difficulty))


@router.post(
    "/calls/{call_id}/answer", response_model=ReplicaOut | None, summary="«Принять» — первая реплика заявителя"
)
async def answer(
    call_id: UUID, body: AnswerIn, actor: Trainee, handler: Annotated[AnswerCallHandler, Depends(deps.provide_answer)]
) -> ReplicaOut | None:
    replica = await handler(AnswerCall(actor=actor, call_id=call_id, card_id=body.card_id))
    return _replica_out(replica) if replica else None


def _replica_out(r: Replica) -> ReplicaOut:
    return ReplicaOut(
        speaker=r.speaker,
        text=r.text,
        message_id=r.message_id,
        tone=r.tone,
        remarks=r.remarks,
        voice=r.voice,
        hung_up=r.hung_up,
    )


@router.post(
    "/calls/dds", response_model=CallStarted, summary="Звонок из АРМ ДДС: старшему группы, заявителю, в службу (п. 2.3)"
)
async def dds_call(
    body: DdsCallIn, actor: Trainee, handler: Annotated[StartDdsCallHandler, Depends(deps.provide_dds_call)]
) -> CallStarted:
    return await handler(
        StartDdsCall(
            actor=actor,
            card_id=body.card_id,
            service_code=body.service_code,
            party=body.party,
            target_service=body.target_service,
            incoming=body.incoming,
            number=body.number,
        )
    )


def _phonebook_out(service_code: str, book: Phonebook | None) -> PhonebookOut:
    entries = book.entries if book else []
    return PhonebookOut(
        service_code=service_code,
        configured=bool(entries),
        entries=[PhonebookEntryOut(role=e.role, title=e.title, name=e.name, number=e.number) for e in entries],
        max_entries=MAX_ENTRIES,
        roles=[ContactRoleOut(code=r, title=t) for r, t in ROLE_TITLES.items()],
        updated_at=book.updated_at if book else None,
    )


@router.get(
    "/dds-phonebook/{service_code}",
    response_model=PhonebookOut,
    summary="Телефонная книга ДДС: абоненты IP-телефона службы (п. 2.3)",
    dependencies=[Depends(require(Permission.TRAINING_PARTICIPATE, Permission.LESSONS_CONDUCT))],
)
async def get_phonebook(
    service_code: str, handler: Annotated[GetPhonebookHandler, Depends(deps.provide_get_phonebook)]
) -> PhonebookOut:
    return _phonebook_out(service_code, await handler(GetPhonebook(service_code=service_code)))


@router.put(
    "/dds-phonebook/{service_code}",
    response_model=PhonebookOut,
    summary="Задать телефонную книгу ДДС целиком: не больше 10 абонентов, номера не повторяются",
)
async def save_phonebook(
    service_code: str,
    body: PhonebookIn,
    actor: Teacher,
    meta: Meta,
    handler: Annotated[SavePhonebookHandler, Depends(deps.provide_save_phonebook)],
) -> PhonebookOut:
    entries = [PhonebookEntry(role=e.role, name=e.name, number=e.number) for e in body.entries]
    book = await handler(SavePhonebook(actor=actor, service_code=service_code, entries=entries, meta=meta))
    return _phonebook_out(book.service_code, book)


@router.post("/calls/{call_id}/replicas", response_model=ReplicaOut, summary="Реплика оператора → ответ ИИ-собеседника")
async def replica(
    call_id: UUID,
    body: ReplicaIn,
    actor: Trainee,
    handler: Annotated[SendReplicaHandler, Depends(deps.provide_replica)],
) -> ReplicaOut:
    signals = TurnSignals(latency_ms=body.latency_ms, interrupted=body.interrupted)
    r = await handler(SendReplica(actor=actor, call_id=call_id, text=body.text, via=body.via, signals=signals))
    return _replica_out(r)


@router.post(
    "/calls/{call_id}/tick",
    response_model=list[ReplicaOut],
    summary="F5: таймер ситуации — реплики-события, если ситуация изменилась сама (раз в 5 с, пока звонок идёт)",
)
async def tick(
    call_id: UUID,
    actor: Trainee,
    handler: Annotated[TickCallHandler, Depends(deps.provide_tick)],
) -> list[ReplicaOut]:
    lock = _CALL_LOCKS.get(call_id)
    if lock is not None and lock.locked():  # идёт ответ на реплику — ситуацию продвинет он
        return []
    return [_replica_out(r) for r in await handler(TickCall(actor=actor, call_id=call_id))]


log = logging.getLogger(__name__)
_CALL_LOCKS: dict[UUID, asyncio.Lock] = {}
_STREAM_TASKS: set[asyncio.Task[None]] = set()


def _sse(kind: str, data: dict[str, Any]) -> bytes:
    return f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n".encode()


@router.post(
    "/calls/{call_id}/replicas/stream",
    summary="Реплика оператора → ответ ИИ-собеседника потоком SSE (F1)",
    description=(
        "События: `accepted` → `state` (состояние заявителя до ответа) → `model` (ответ пишет модель; нет события — "
        "ответ по правилам) → `offline`? (модель недоступна, ответ по правилам) → `token`* / `remark`* → `replace`? "
        "(ответ модели отклонён проверкой, итоговый текст — "
        "в `final`) → `final` (как ответ `POST /replicas` + `metrics`) или `error`. Сохранение — после ответа "
        "целиком; обрыв соединения генерацию не отменяет, чтобы реплика не потерялась."
    ),
)
async def replica_stream(
    call_id: UUID,
    body: ReplicaIn,
    actor: Trainee,
    factory: Annotated[StreamReplicaFactory, Depends(deps.provide_replica_stream)],
) -> StreamingResponse:
    signals = TurnSignals(latency_ms=body.latency_ms, interrupted=body.interrupted)
    cmd = SendReplica(actor=actor, call_id=call_id, text=body.text, via=body.via, signals=signals)
    queue: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()

    async def sink(kind: str, data: dict[str, Any]) -> None:
        await queue.put((kind, data))

    async def run() -> None:
        lock = _CALL_LOCKS.setdefault(call_id, asyncio.Lock())  # реплики одного звонка — строго по очереди
        try:
            async with lock, factory() as handler:
                r = await handler(cmd, sink=sink)
            await queue.put(("final", _replica_out(r).model_dump(mode="json")))
        except AppError as e:
            if isinstance(e, ExternalServiceError):
                log.warning("Потоковый ответ звонка %s: %s", call_id, e.message)
            await queue.put(("error", {"code": e.code, "message": e.public_message}))
        except Exception:
            log.exception("Потоковый ответ звонка %s не удался", call_id)
            await queue.put(("error", {"code": "internal_error", "message": "Не удалось получить ответ собеседника"}))
        finally:
            if not lock.locked():
                _CALL_LOCKS.pop(call_id, None)
            await queue.put(None)

    task = asyncio.create_task(run())
    _STREAM_TASKS.add(task)  # ссылка на задачу: без неё её может собрать сборщик мусора
    task.add_done_callback(_STREAM_TASKS.discard)

    async def events() -> AsyncIterator[bytes]:
        started = time.perf_counter()
        first_token: float | None = None
        pieces = 0
        model: dict[str, Any] | None = None
        replaced = False
        remarks = RemarkFilter()
        yield _sse("accepted", {})
        while (item := await queue.get()) is not None:
            kind, data = item
            if kind == "model":
                model = data
            elif kind == "offline":  # модель недоступна до первого куска — ответ по правилам
                model = None
            elif kind == "replace":
                replaced = True
            elif kind == "token":
                text = remarks.feed(str(data.get("text", "")))
                for r in remarks.take_remarks():
                    yield _sse("remark", {"text": r})
                if not text:
                    continue
                pieces += 1
                if first_token is None:
                    first_token = time.perf_counter()
                data = {"text": text}
            elif kind == "final":
                total = time.perf_counter() - started
                gen = total - (first_token - started) if first_token else 0.0
                data = {
                    **data,
                    "metrics": {
                        "source": "llm" if model and not replaced else "rules",
                        "model": model.get("model") if model else None,
                        "ttft_ms": round((first_token - started) * 1000) if first_token else None,
                        "total_ms": round(total * 1000),
                        "pieces": pieces,
                        "pieces_per_s": round(pieces / gen, 1) if gen > 0.05 else None,
                        "replaced": replaced,
                    },
                }
            yield _sse(kind, data)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},  # nginx не копит поток
    )


@router.get(
    "/calls/{call_id}/speak",
    summary="Озвучить фразу потокового ответа голосом собеседника (F1)",
    responses={200: {"content": {"audio/wav": {}, "audio/mpeg": {}}}},
)
async def speak_fragment(
    call_id: UUID,
    actor: Trainee,
    handler: Annotated[SpeakFragmentHandler, Depends(deps.provide_speak_fragment)],
    text: Annotated[str, QueryParam(min_length=1, max_length=400)],
    emotion: Annotated[str | None, QueryParam(max_length=20)] = None,
    pace: Annotated[str, QueryParam(max_length=12)] = "normal",
    volume: Annotated[str, QueryParam(max_length=12)] = "normal",
    breathing: Annotated[str, QueryParam(max_length=12)] = "calm",
    tension: Annotated[int | None, QueryParam(ge=0, le=10, description="F3: напряжение заявителя 0–10")] = None,
    level: Annotated[int | None, QueryParam(ge=1, le=5, description="F3: уровень ECCS при профиле")] = None,
    remarks: Annotated[
        list[str] | None, QueryParam(max_length=4, description="F3: ремарки перед фразой: плачет, задыхается…")
    ] = None,
) -> Response:
    audio = await handler(
        SpeakFragment(
            actor=actor,
            call_id=call_id,
            text=text,
            emotion=emotion,
            pace=pace,
            volume=volume,
            breathing=breathing,
            tension=tension,
            level=level,
            remarks=tuple(r[:40] for r in remarks or ()),
        )
    )
    return Response(content=audio.content, media_type=audio.mime, headers={"Cache-Control": "private, max-age=600"})


class SpeechOut(BaseModel):
    text: str


class SpeechStatusOut(BaseModel):
    enabled: bool = Field(description="Голосовой ввод: модель распознавания настроена")
    tts: bool = Field(default=False, description="Серверный синтез голоса собеседника; нет — озвучивает браузер")


@router.get("/speech", response_model=SpeechStatusOut, summary="Что из речи настроено: распознавание и синтез")
async def speech_status(
    _: Trainee, status: Annotated[SpeechStatus, Depends(deps.provide_speech_status)]
) -> SpeechStatusOut:
    return SpeechStatusOut(enabled=status.stt, tts=status.tts)


@router.post("/speech", response_model=SpeechOut, summary="Распознать реплику в трубку (голосовой ввод, Whisper)")
async def transcribe(
    actor: Trainee,
    handler: Annotated[TranscribeHandler, Depends(deps.provide_transcribe)],
    audio: Annotated[UploadFile, File(description="Запись из браузера: webm/ogg/wav, до 3 МБ")],
) -> SpeechOut:
    data = await audio.read()
    r = await handler(Transcribe(actor=actor, audio=data, mime=audio.content_type or "audio/webm"))
    return SpeechOut(text=r.text)


class VoiceLabSttIn(BaseModel):
    audio: str = Field(max_length=6_000_000, description="Запись из браузера в base64")
    format: str = Field(default="webm", max_length=10)
    language: str = Field(default="auto", max_length=10)


class VoiceLabMessage(BaseModel):
    role: str = Field(max_length=20)
    content: str = Field(max_length=12000)


class VoiceLabChatIn(BaseModel):
    messages: list[VoiceLabMessage] = Field(min_length=1, max_length=60)


class VoiceLabTtsIn(BaseModel):
    input: str = Field(min_length=1, max_length=4600)
    voice: str | None = Field(default=None, max_length=40)


@router.post("/voice-lab/stt", summary="Голосовой полигон: распознать фразу (п. 3.6)")
async def voice_lab_stt(
    _: Trainee, lab: Annotated[VoiceLab, Depends(deps.provide_voice_lab)], body: VoiceLabSttIn
) -> dict[str, str]:
    try:
        audio = base64.b64decode(body.audio, validate=True)
    except (ValueError, binascii.Error) as e:
        raise DomainError("Запись повреждена", code="bad_audio") from e
    fmt = re.sub(r"[^a-z0-9]", "", body.format.lower()) or "webm"
    return {"text": await lab.transcribe(audio, mime=f"audio/{fmt}")}


@router.post("/voice-lab/chat", summary="Голосовой полигон: ответ заявителя потоком SSE (п. 3.6)")
async def voice_lab_chat(
    _: Trainee, lab: Annotated[VoiceLab, Depends(deps.provide_voice_lab)], body: VoiceLabChatIn
) -> StreamingResponse:
    messages = [LabMessage(role=m.role, content=m.content) for m in body.messages]
    pieces = lab.stream_reply(messages)
    first = await anext(pieces, None)  # ошибка модели до первого куска — обычный ответ с ошибкой, а не обрыв потока

    async def events() -> AsyncIterator[bytes]:
        # формат потока OpenRouter/OpenAI, который читает страница: куски по мере генерации, затем [DONE]
        def chunk(part: str) -> bytes:
            return f"data: {json.dumps({'choices': [{'delta': {'content': part}}]}, ensure_ascii=False)}\n\n".encode()

        if first:
            yield chunk(first)
        try:
            async for part in pieces:
                yield chunk(part)
        except AppError as e:
            log.warning("Полигон: поток модели прерван: %s", e)
        yield b"data: [DONE]\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})


@router.post("/voice-lab/tts", summary="Голосовой полигон: озвучить реплику с эмоцией (п. 3.6)")
async def voice_lab_tts(
    _: Trainee, lab: Annotated[VoiceLab, Depends(deps.provide_voice_lab)], body: VoiceLabTtsIn
) -> Response:
    audio = await lab.speak(body.input)
    return Response(content=audio.content, media_type=audio.mime, headers={"Cache-Control": "no-store"})


@router.post("/calls/{call_id}/end", response_model=StatusOut, summary="Завершить звонок")
async def end_call(
    call_id: UUID, actor: Trainee, meta: Meta, handler: Annotated[EndCallHandler, Depends(deps.provide_end_call)]
) -> StatusOut:
    return StatusOut(status=await handler(EndCall(actor=actor, call_id=call_id, meta=meta)))


class HoldOut(BaseModel):
    status: str
    held_s: int = 0
    hung_up: bool = Field(default=False, description="Заявитель не дождался на удержании и положил трубку")


@router.post("/calls/{call_id}/hold", response_model=HoldOut, summary="Поставить звонок на удержание (ТЗ 6.1)")
async def hold_call(
    call_id: UUID, actor: Trainee, meta: Meta, handler: Annotated[HoldCallHandler, Depends(deps.provide_hold_call)]
) -> HoldOut:
    r = await handler(HoldCall(actor=actor, call_id=call_id, hold=True, meta=meta))
    return HoldOut(status=r.status, held_s=r.held_s, hung_up=r.hung_up)


@router.post("/calls/{call_id}/resume", response_model=HoldOut, summary="Снять звонок с удержания (ТЗ 6.1)")
async def resume_call(
    call_id: UUID, actor: Trainee, meta: Meta, handler: Annotated[HoldCallHandler, Depends(deps.provide_hold_call)]
) -> HoldOut:
    r = await handler(HoldCall(actor=actor, call_id=call_id, hold=False, meta=meta))
    return HoldOut(status=r.status, held_s=r.held_s, hung_up=r.hung_up)


@router.post(
    "/calls/{call_id}/pause",
    response_model=StatusOut,
    summary="«Пауза»: обучающийся останавливает тяжёлый звонок, блок «Работа с заявителем» не оценивается (п. 3.7)",
)
async def pause_call(
    call_id: UUID, actor: Trainee, meta: Meta, handler: Annotated[PauseCallHandler, Depends(deps.provide_pause_call)]
) -> StatusOut:
    return StatusOut(status=await handler(PauseCall(actor=actor, call_id=call_id, meta=meta)))


@router.get(
    "/psy/profiles",
    response_model=list[PsyProfileOut],
    summary="Каталог психологических профилей заявителя (п. 3.7)",
)
async def psy_profiles(
    _: Annotated[Principal, Depends(require(Permission.LESSONS_CONDUCT, Permission.SCENARIOS_MANAGE))],
    catalog: Annotated[PsyCatalog, Depends(deps.provide_psy_catalog)],
) -> list[PsyProfileOut]:
    return [
        PsyProfileOut(
            id=p.id,
            title=p.title,
            group=p.group,
            sensitive=p.sensitive,
            pinned_only=p.pinned_only,
            start=p.start,
            floor=p.floor,
            pool=p.pool,
            key_acts=sorted(p.key_acts),
            critical=sorted(p.critical),
            required_routing=list(p.required_routing),
            speech=dict(p.speech),
            sources=list(p.sources),
        )
        for p in catalog.profiles().values()
    ]


@router.get(
    "/psy/methodology",
    response_model=MethodologyView,
    summary="Методика модификатора: научно-методическая основа и профили карточками (F4)",
)
async def psy_methodology(
    _: Annotated[Principal, Depends(require(Permission.DICTIONARIES_READ))],
    handler: Annotated[PsyMethodologyHandler, Depends(deps.provide_psy_methodology)],
) -> MethodologyView:
    return await handler(GetPsyMethodology())


@router.post(
    "/scenarios/{scenario_id}/psy",
    response_model=StatusOut,
    summary="Закрепить за сценарием психологический профиль заявителя (п. 3.7)",
)
async def set_scenario_psy(
    scenario_id: UUID,
    body: ScenarioPsyIn,
    actor: Manager,
    meta: Meta,
    handler: Annotated[SetScenarioPsyHandler, Depends(deps.provide_set_scenario_psy)],
) -> StatusOut:
    profile = await handler(SetScenarioPsy(actor=actor, scenario_id=scenario_id, profile=body.profile, meta=meta))
    return StatusOut(status=profile or "none")


@router.get("/calls/{call_id}", response_model=CallView, summary="Звонок с репликами")
async def get_call(
    call_id: UUID, actor: CurrentPrincipal, handler: Annotated[GetCallHandler, Depends(deps.provide_get_call)]
) -> CallView:
    return await handler(GetCall(actor=actor, call_id=call_id))


@router.get(
    "/calls/{call_id}/messages/{message_id}/audio",
    response_class=Response,
    responses={200: {"content": {"audio/mpeg": {}, "audio/wav": {}}, "description": "Звук реплики"}},
    summary="Звук реплики собеседника: серверный синтез с подачей по состоянию заявителя (п. 3.6)",
)
async def replica_audio(
    call_id: UUID,
    message_id: UUID,
    actor: CurrentPrincipal,
    handler: Annotated[ReplicaAudioHandler, Depends(deps.provide_replica_audio)],
) -> Response:
    audio = await handler(GetReplicaAudio(actor=actor, call_id=call_id, message_id=message_id))
    return Response(content=audio.content, media_type=audio.mime)


@router.get(
    "/calls/{call_id}/recording",
    response_class=Response,
    responses={200: {"content": {"audio/wav": {}, "audio/mpeg": {}}, "description": "Запись звонка одним файлом"}},
    summary="Запись звонка (п. 8.7): все реплики, озвученные серверным синтезом, одним файлом WAV (или MP3)",
)
async def call_recording(
    call_id: UUID,
    actor: CurrentPrincipal,
    handler: Annotated[CallRecordingHandler, Depends(deps.provide_call_recording)],
) -> Response:
    rec = await handler(GetCallRecording(actor=actor, call_id=call_id))
    return Response(
        content=rec.content,
        media_type=rec.mime,
        headers={"Content-Disposition": f'attachment; filename="{rec.file_name}"'},
    )


@router.get("/cards/{card_id}/calls", response_model=list[CallView], summary="Звонки по карточке")
async def card_calls(
    card_id: UUID, actor: CurrentPrincipal, handler: Annotated[CardCallsHandler, Depends(deps.provide_card_calls)]
) -> list[CallView]:
    return await handler(CardCalls(actor=actor, card_id=card_id))


class GrammarRemark(BaseModel):
    field: str
    quote: str
    fix: str
    rule: str


class EditScenarioOut(BaseModel):
    status: str
    grammar: list[GrammarRemark] = Field(default_factory=list, description="Замечания проверки грамотности (п. 3.6)")
    checked_by: str = Field(description="rules — правила; rules+model — правила и модель")


@router.patch(
    "/scenarios/{scenario_id}",
    response_model=EditScenarioOut,
    summary="Правка сценария (возвращает в черновики) с проверкой грамотности",
)
async def edit_scenario(
    scenario_id: UUID,
    body: EditScenarioIn,
    actor: Manager,
    meta: Meta,
    handler: Annotated[EditScenarioHandler, Depends(deps.provide_edit_scenario)],
) -> EditScenarioOut:
    r = await handler(EditScenario(actor=actor, scenario_id=scenario_id, meta=meta, **body.model_dump()))
    return EditScenarioOut(
        status=r.status,
        grammar=[GrammarRemark(field=g.field, quote=g.quote, fix=g.fix, rule=g.rule) for g in r.grammar],
        checked_by=r.checked_by,
    )


@router.put(
    "/scenarios/{scenario_id}/answers/{topic}",
    response_model=EditScenarioOut,
    summary="Один ответ заявителя из прогона: вручную или по комментарию моделью (ТЗ 3.4); сценарий — в черновики",
)
async def edit_answer(
    scenario_id: UUID,
    topic: str,
    body: EditAnswerIn,
    actor: Manager,
    meta: Meta,
    handler: Annotated[EditAnswerHandler, Depends(deps.provide_edit_answer)],
) -> EditScenarioOut:
    r = await handler(
        EditAnswer(actor=actor, scenario_id=scenario_id, topic=topic, text=body.text, comment=body.comment, meta=meta)
    )
    return EditScenarioOut(
        status=r.status,
        grammar=[GrammarRemark(field=g.field, quote=g.quote, fix=g.fix, rule=g.rule) for g in r.grammar],
        checked_by=r.checked_by,
    )


@router.get(
    "/scenarios/{scenario_id}/preview", response_model=list[PreviewItem], summary="Прогон: вопросы оператора и ответы"
)
async def preview_scenario(
    scenario_id: UUID, _: Manager, handler: Annotated[PreviewScenarioHandler, Depends(deps.provide_preview)]
) -> list[PreviewItem]:
    return await handler(PreviewScenario(scenario_id=scenario_id))


@router.get("/students", response_model=list[StudentRow], summary="Обучающиеся для назначения на занятие")
async def students(
    _: Teacher, handler: Annotated[ListStudentsHandler, Depends(deps.provide_students)]
) -> list[StudentRow]:
    return await handler(ListStudents())


@router.post("/sessions", response_model=CreatedOut, status_code=201, summary="Создать занятие (п. 4.2)")
async def create_session(
    body: CreateSessionIn,
    actor: Teacher,
    meta: Meta,
    handler: Annotated[CreateSessionHandler, Depends(deps.provide_create_session)],
) -> CreatedOut:
    sid = await handler(
        CreateSession(
            actor=actor,
            title=body.title,
            mode=body.mode,
            card_source=body.card_source,
            groups=body.groups,
            participants=[ParticipantIn(p.student_id, p.role, p.dds_service_code) for p in body.participants],
            settings=body.settings.model_dump(exclude_none=True),
            meta=meta,
        )
    )
    return CreatedOut(id=sid)


@router.get("/session-defaults", summary="Тайминг и пороги занятия по умолчанию (настройки администратора)")
async def session_defaults(
    _: Teacher, handler: Annotated[GetSessionDefaultsHandler, Depends(deps.provide_session_defaults)]
) -> dict[str, Any]:
    return await handler(GetSessionDefaults())


@router.get("/sessions", response_model=SessionPage, summary="Мои занятия (преподаватель)")
async def list_sessions(
    actor: Teacher,
    handler: Annotated[ListSessionsHandler, Depends(deps.provide_list_sessions)],
    page: int = 1,
    page_size: int = 30,
) -> SessionPage:
    return await handler(ListSessions(actor=actor, page=page, page_size=page_size))


@router.get("/sessions/my", response_model=MySessionView | None, summary="Идущее занятие обучающегося и его роль")
async def my_session(
    actor: CurrentPrincipal, handler: Annotated[MySessionHandler, Depends(deps.provide_my_session)]
) -> MySessionView | None:
    return await handler(MySession(actor=actor))


@router.get("/sessions/mine", response_model=list[MySessionRow], summary="Мои занятия: назначенные, идущее, прошедшие")
async def my_sessions(
    actor: Trainee, handler: Annotated[MySessionsHandler, Depends(deps.provide_my_sessions)]
) -> list[MySessionRow]:
    return await handler(MySessions(actor=actor))


@router.post("/sessions/feed", response_model=FeedResult, summary="Выпустить карточку занятия в очередь своей ДДС")
async def feed(actor: Trainee, handler: Annotated[FeedDdsCardHandler, Depends(deps.provide_feed)]) -> FeedResult:
    return await handler(FeedDdsCard(actor=actor))


class SelfCardIn(BaseModel):
    service_code: str = Field(min_length=1, max_length=32, description="Код службы ДДС")


@router.post(
    "/self-training/dds",
    response_model=SelfCardIssued,
    status_code=201,
    summary="Самостоятельная тренировка ДДС: учебная карточка вне занятия для своей службы",
)
async def dds_self_card(
    body: SelfCardIn,
    actor: Trainee,
    meta: Meta,
    handler: Annotated[RequestDdsSelfCardHandler, Depends(deps.provide_self_card)],
) -> SelfCardIssued:
    return await handler(RequestDdsSelfCard(actor=actor, service_code=body.service_code, meta=meta))


@router.get("/sessions/{session_id}", response_model=SessionView, summary="Занятие")
async def get_session(
    session_id: UUID, actor: Teacher, handler: Annotated[GetSessionHandler, Depends(deps.provide_get_session)]
) -> SessionView:
    return await handler(GetSession(actor=actor, session_id=session_id))


@router.get(
    "/sessions/{session_id}/monitor", response_model=MonitorView, summary="Мониторинг занятия в реальном времени"
)
async def monitor(
    session_id: UUID, actor: Teacher, handler: Annotated[SessionMonitorHandler, Depends(deps.provide_monitor)]
) -> MonitorView:
    return await handler(SessionMonitor(actor=actor, session_id=session_id))


@router.post("/sessions/{session_id}/start", response_model=StatusOut, summary="Начать занятие")
async def start_session(
    session_id: UUID,
    actor: Teacher,
    meta: Meta,
    handler: Annotated[ChangeSessionStateHandler, Depends(deps.provide_session_state)],
) -> StatusOut:
    return StatusOut(
        status=await handler(ChangeSessionState(actor=actor, session_id=session_id, start=True, meta=meta))
    )


@router.post("/sessions/{session_id}/finish", response_model=StatusOut, summary="Завершить занятие")
async def finish_session(
    session_id: UUID,
    actor: Teacher,
    meta: Meta,
    handler: Annotated[ChangeSessionStateHandler, Depends(deps.provide_session_state)],
) -> StatusOut:
    return StatusOut(
        status=await handler(ChangeSessionState(actor=actor, session_id=session_id, start=False, meta=meta))
    )


# ------------------------------------------------------------------ п. 4.4: учебные материалы
MaterialsManager = Annotated[Principal, Depends(require(Permission.SCENARIOS_MANAGE, Permission.SYSTEM_MANAGE))]


class MaterialPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=3, max_length=200)
    kind: MaterialKind | None = None
    visible: bool | None = None
    use_in_prompts: bool | None = None


class MaterialFilesPort(Protocol):
    def path(self, material_id: UUID) -> Path: ...


@router.post("/materials", response_model=CreatedOut, status_code=201, summary="Загрузить учебный материал")
async def upload_material(
    actor: MaterialsManager,
    meta: Meta,
    handler: Annotated[UploadMaterialHandler, Depends(deps.provide_upload_material)],
    file: Annotated[UploadFile, File(description="PDF, DOCX, XLSX, TXT или MD, до 25 МБ")],
    title: Annotated[str, Form(min_length=3, max_length=200)],
    kind: Annotated[MaterialKind, Form()] = MaterialKind.OTHER,
    visible: Annotated[bool, Form()] = True,
    use_in_prompts: Annotated[bool, Form()] = False,
) -> CreatedOut:
    data = await file.read(MAX_BYTES + 1)
    mid = await handler(
        UploadMaterial(
            actor=actor,
            title=title,
            kind=kind,
            filename=file.filename or "file",
            data=data,
            visible=visible,
            use_in_prompts=use_in_prompts,
            meta=meta,
        )
    )
    return CreatedOut(id=mid)


@router.get("/materials", response_model=list[MaterialRow], summary="Учебные материалы (обучающимся — опубликованные)")
async def list_materials(
    actor: CurrentPrincipal, handler: Annotated[ListMaterialsHandler, Depends(deps.provide_list_materials)], q: str = ""
) -> list[MaterialRow]:
    return await handler(ListMaterials(actor=actor, q=q))


@router.get("/materials/{material_id}", response_model=MaterialView, summary="Материал: текст и найденные места")
async def get_material(
    material_id: UUID,
    actor: CurrentPrincipal,
    handler: Annotated[GetMaterialHandler, Depends(deps.provide_get_material)],
    q: str = "",
) -> MaterialView:
    return await handler(GetMaterial(actor=actor, material_id=material_id, q=q))


@router.get("/materials/{material_id}/file", summary="Файл материала (PDF открывается в браузере)")
async def material_file(
    material_id: UUID,
    actor: CurrentPrincipal,
    handler: Annotated[GetMaterialHandler, Depends(deps.provide_get_material)],
    files: Annotated[MaterialFilesPort, Depends(deps.provide_material_files)],
    download: bool = False,
) -> FileResponse:
    view = await handler(GetMaterial(actor=actor, material_id=material_id))
    path = files.path(material_id)
    if not path.is_file():
        raise NotFoundError("Файл материала не найден в хранилище", code="material_file_missing")
    inline = view.file_type == "pdf" and not download
    return FileResponse(
        path,
        media_type=view.content_type,
        filename=view.filename,
        content_disposition_type="inline" if inline else "attachment",
    )


@router.patch("/materials/{material_id}", response_model=StatusOut, summary="Изменить материал")
async def update_material(
    material_id: UUID,
    body: MaterialPatchIn,
    actor: MaterialsManager,
    meta: Meta,
    handler: Annotated[UpdateMaterialHandler, Depends(deps.provide_update_material)],
) -> StatusOut:
    await handler(UpdateMaterial(actor=actor, material_id=material_id, meta=meta, **body.model_dump()))
    return StatusOut(status="ok")


@router.delete("/materials/{material_id}", status_code=204, summary="Удалить материал")
async def delete_material(
    material_id: UUID,
    actor: MaterialsManager,
    meta: Meta,
    handler: Annotated[DeleteMaterialHandler, Depends(deps.provide_delete_material)],
) -> None:
    await handler(DeleteMaterial(actor=actor, material_id=material_id, meta=meta))
