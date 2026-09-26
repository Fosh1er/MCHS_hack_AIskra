"""HTTP-схемы (pydantic) модуля system. Отделены от DTO application-слоя."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProbeRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000, examples=["Скажи «готов», если слышишь меня"])
    task: str = Field(default="probe", examples=["probe", "applicant_actor"])


class ProbeResponse(BaseModel):
    task: str
    provider: str
    model: str
    text: str
    cached: bool
    latency_ms: int


class TaskInfoOut(BaseModel):
    task: str
    provider: str
    model: str
    temperature: float
    cache_mode: str
    cache_ttl_s: int


class AIConfigOut(BaseModel):
    allow_external: bool
    default_provider: str
    tasks: list[TaskInfoOut]
