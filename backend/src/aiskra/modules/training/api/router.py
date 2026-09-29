"""HTTP-адаптер training: банк сценариев (3.2) и учебные звонки (1.4, 2.3)."""

from __future__ import annotations

import base64
import binascii
import json
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, Any, Protocol
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from aiskra.modules.training.api import deps
from aiskra.modules.training.api.schemas import (
    AnswerIn,
    CreatedOut,
    CreateSessionIn,
    DdsCallIn,
    EditScenarioIn,
    GeneratedOut,
    GenerateIn,
    IncomingIn,
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
    PauseCall,
    PauseCallHandler,
    Replica,
    SendReplica,
    SendReplicaHandler,
    StartDdsCall,
    StartDdsCallHandler,
    StartIncomingCall,
    StartIncomingCallHandler,
)
from aiskra.modules.training.application.commands.materials import (
    DeleteMaterial,
    DeleteMaterialHandler,
    UpdateMaterial,
    UpdateMaterialHandler,
    UploadMaterial,
    UploadMaterialHandler,
)
from aiskra.modules.training.application.commands.scenario_review import (
    ReviewSections,
    ReviewSectionsHandler,
    SectionsReviewed,
)
from aiskra.modules.training.application.commands.scenarios import (
    EditScenario,
    EditScenarioHandler,
    GenerateScenarios,
    GenerateScenariosHandler,
    ReviewScenario,
    ReviewScenarioHandler,
    SetScenarioPsy,
    SetScenarioPsyHandler,
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
from aiskra.modules.training.application.ports.materials import MaterialRow
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
    SpeechStatus,
    Transcribe,
    TranscribeHandler,
)
from aiskra.modules.training.application.voice_lab import LabMessage, VoiceLab
from aiskra.modules.training.domain.material import MAX_BYTES, MaterialKind
from aiskra.modules.training.domain.review import Decision
from aiskra.shared.errors import DomainError, NotFoundError
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
        GenerateScenarios(actor=actor, count=body.count, groups=body.groups, difficulty=body.difficulty, meta=meta)
    )
    return GeneratedOut(ids=ids)


@router.get("/scenarios", response_model=ScenarioPage, summary="Банк сценариев")
async def list_scenarios(
    _: Manager,
    handler: Annotated[ListScenariosHandler, Depends(deps.provide_list_scenarios)],
    status: str | None = None,
    difficulty: int | None = None,
    card_type: str | None = None,
    source: str | None = None,
    page: int = 1,
    page_size: int = 30,
) -> ScenarioPage:
    return await handler(
        ListScenarios(
            status=status, difficulty=difficulty, card_type=card_type, source=source, page=page, page_size=page_size
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
        )
    )


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
    text = await lab.reply([LabMessage(role=m.role, content=m.content) for m in body.messages])

    async def events() -> AsyncIterator[bytes]:
        # формат потока OpenRouter/OpenAI, который читает страница: фразами, затем [DONE]
        for part in re.findall(r"[^.!?…\n]+[.!?…\n]*\s*", text) or [text]:
            yield f"data: {json.dumps({'choices': [{'delta': {'content': part}}]}, ensure_ascii=False)}\n\n".encode()
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
