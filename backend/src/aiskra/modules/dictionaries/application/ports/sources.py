"""Порты источников справочников и записи в хранилище."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from aiskra.modules.dictionaries.domain.model import IncidentType, ServiceColumn


@dataclass
class ClassifierSheet:
    """Сырой лист классификатора: заголовки групп колонок и строки как есть (разбор — в домене)."""

    file_name: str
    file_sha256: str
    column_headers: dict[int, str]  # Excel-колонка (с 1) → заголовок группы (протянут вправо)
    group_titles: dict[int, str]  # строки-заголовки групп: номер → название
    rows: list[tuple[Any, ...]]  # строки типов происшествий (значения ячеек)


@dataclass
class CuratedDictionaries:
    """Выверенные справочники из data/dictionaries/*.yaml (как есть, словари)."""

    okrugs: list[dict[str, Any]]
    districts: list[dict[str, Any]]
    services: list[dict[str, Any]]
    enums: dict[str, list[dict[str, Any]]]
    channels: list[dict[str, Any]]
    card_types: list[dict[str, Any]]
    columns: list[dict[str, Any]]


class ClassifierSource(Protocol):
    def read(self) -> ClassifierSheet: ...


class CuratedSource(Protocol):
    def read(self) -> CuratedDictionaries: ...


@dataclass
class DictionaryPayload:
    """Всё, что записывается одной транзакцией."""

    source_file: str
    source_sha256: str
    groups: dict[int, str]
    incident_types: list[IncidentType]
    columns: list[ServiceColumn]
    services: list[dict[str, Any]]
    okrugs: list[dict[str, Any]]
    districts: list[dict[str, Any]]
    enums: dict[str, list[dict[str, Any]]]
    channels: list[dict[str, Any]]
    card_types: list[dict[str, Any]]


@dataclass
class WriteStats:
    counts: dict[str, int] = field(default_factory=dict)
    deactivated: dict[str, int] = field(default_factory=dict)


class DictionaryWriter(Protocol):
    async def replace(self, payload: DictionaryPayload) -> WriteStats: ...
