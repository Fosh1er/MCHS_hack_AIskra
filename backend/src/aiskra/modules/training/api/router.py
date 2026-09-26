"""HTTP-адаптер training: банк сценариев (3.2) и учебные звонки (1.4, 2.3)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from aiskra.modules.training.api import deps
from aiskra.modules.training.api.schemas import (
    AnswerIn,
    DdsCallIn,
    GeneratedOut,
    GenerateIn,
    IncomingIn,
    ReplicaIn,
    ReplicaOut,
    StatusOut,
)
from aiskra.modules.training.application.commands.calls import (
    AnswerCall,
    AnswerCallHandler,
    CallStarted,
    EndCall,
    EndCallHandler,
    SendReplica,
    SendReplicaHandler,
    StartDdsCall,
    StartDdsCallHandler,
    StartIncomingCall,
    StartIncomingCallHandler,
)
from aiskra.modules.training.application.commands.scenarios import (
    GenerateScenarios,
    GenerateScenariosHandler,
    ReviewScenario,
    ReviewScenarioHandler,
)
from aiskra.modules.training.application.queries.calls import (
    CallView,
    CardCalls,
    CardCallsHandler,
    GetCall,
    GetCallHandler,
)
from aiskra.modules.training.application.queries.scenarios import (
    GetScenario,
    GetScenarioHandler,
    ListScenarios,
    ListScenariosHandler,
    ScenarioPage,
    ScenarioView,
)
from aiskra.shared.security import Permission, Principal
from aiskra.shared.web import CurrentPrincipal, Meta, require

router = APIRouter(prefix="/training", tags=["training"])
Manager = Annotated[Principal, Depends(require(Permission.SCENARIOS_MANAGE))]
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
    page: int = 1,
    page_size: int = 30,
) -> ScenarioPage:
    return await handler(ListScenarios(status=status, page=page, page_size=page_size))


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
    return ReplicaOut(speaker=replica.speaker, text=replica.text) if replica else None


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
    r = await handler(SendReplica(actor=actor, call_id=call_id, text=body.text))
    return ReplicaOut(speaker=r.speaker, text=r.text)


@router.post("/calls/{call_id}/end", response_model=StatusOut, summary="Завершить звонок")
async def end_call(
    call_id: UUID, actor: Trainee, meta: Meta, handler: Annotated[EndCallHandler, Depends(deps.provide_end_call)]
) -> StatusOut:
    return StatusOut(status=await handler(EndCall(actor=actor, call_id=call_id, meta=meta)))


@router.get("/calls/{call_id}", response_model=CallView, summary="Звонок с репликами")
async def get_call(
    call_id: UUID, actor: CurrentPrincipal, handler: Annotated[GetCallHandler, Depends(deps.provide_get_call)]
) -> CallView:
    return await handler(GetCall(actor=actor, call_id=call_id))


@router.get("/cards/{card_id}/calls", response_model=list[CallView], summary="Звонки по карточке")
async def card_calls(
    card_id: UUID, actor: CurrentPrincipal, handler: Annotated[CardCallsHandler, Depends(deps.provide_card_calls)]
) -> list[CallView]:
    return await handler(CardCalls(actor=actor, card_id=card_id))
