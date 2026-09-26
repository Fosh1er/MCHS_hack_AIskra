"""Порты учебных материалов (п. 4.4)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID

from aiskra.modules.training.domain.material import FileType, Material


@dataclass(frozen=True)
class MaterialRow:
    id: UUID
    title: str
    kind: str
    filename: str
    file_type: str
    size_bytes: int
    visible: bool
    use_in_prompts: bool
    created_at: datetime | None
    text_chars: int
    uploaded_by_name: str | None = None


class MaterialRepository(Protocol):
    async def add(self, m: Material) -> None: ...

    async def get(self, material_id: UUID) -> Material | None: ...

    async def save(self, m: Material) -> None: ...

    async def delete(self, material_id: UUID) -> None: ...

    async def rows(self, *, q: str, visible_only: bool) -> list[MaterialRow]: ...

    async def prompt_texts(self) -> list[tuple[str, str]]: ...

    async def by_sha(self, sha256: str) -> Material | None: ...


class FileStorage(Protocol):
    def put(self, material_id: UUID, data: bytes) -> None: ...

    def path(self, material_id: UUID) -> Path: ...

    def delete(self, material_id: UUID) -> None: ...


class TextExtractor(Protocol):
    def extract(self, data: bytes, file_type: FileType) -> str: ...


class MaterialContext(Protocol):
    """Выдержки из материалов для промпта генерации (R4.4-06)."""

    async def snippets(self, query: str, limit: int = 3) -> list[tuple[str, str]]: ...
