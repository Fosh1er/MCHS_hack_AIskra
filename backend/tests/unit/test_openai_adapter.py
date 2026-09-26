import json

import httpx
import pytest
from pydantic import BaseModel

from aiskra.ai.adapters.openai_compatible import OpenAICompatibleLLM
from aiskra.ai.ports import ChatMessage, LLMParams
from aiskra.shared.errors import ExternalServiceError


class Verdict(BaseModel):
    score: int


def reply(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}}], "usage": {"prompt_tokens": 10, "completion_tokens": 3}},
    )


def make(handler) -> OpenAICompatibleLLM:  # type: ignore[no-untyped-def]
    return OpenAICompatibleLLM(
        name="local", base_url="http://llm:8080/v1", model="m", transport=httpx.MockTransport(handler)
    )


async def test_plain_completion_and_request_shape() -> None:
    seen: dict[str, object] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(json.loads(req.content))
        assert req.url.path == "/v1/chat/completions"
        return reply("Готов")

    llm = make(handler)
    r = await llm.complete([ChatMessage("user", "Привет")], params=LLMParams(task="probe", temperature=0))
    assert r.text == "Готов" and r.usage.prompt_tokens == 10
    assert seen["model"] == "m" and seen["temperature"] == 0


async def test_structured_output_with_fence_and_one_retry() -> None:
    answers = iter(["не json", '```json\n{"score": 5}\n```'])

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        assert body["response_format"]["type"] == "json_schema"
        return reply(next(answers))

    r = await make(handler).complete([ChatMessage("user", "Оцени")], params=LLMParams(task="judge"), schema=Verdict)
    assert isinstance(r.parsed, Verdict) and r.parsed.score == 5


async def test_unavailable_model_raises_service_error() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(502)

    with pytest.raises(ExternalServiceError, match="недоступна"):
        await make(handler).complete([ChatMessage("user", "x")], params=LLMParams(task="probe"))
