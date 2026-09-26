"""Адаптеры источников: xlsx-классификатор (openpyxl) и выверенные YAML-справочники."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import openpyxl
import yaml

from aiskra.modules.dictionaries.application.ports.sources import ClassifierSheet, CuratedDictionaries
from aiskra.shared.errors import DomainError

HEADER_ROWS = 3  # строки заголовков: группа колонок / подзаголовок / условие


class XlsxClassifierSource:
    def __init__(self, path: Path) -> None:
        self._path = path

    def read(self) -> ClassifierSheet:
        if not self._path.exists():
            raise DomainError(f"Файл классификатора не найден: {self._path}", code="source_missing")
        digest = hashlib.sha256(self._path.read_bytes()).hexdigest()
        wb = openpyxl.load_workbook(self._path, read_only=True, data_only=True)
        try:
            ws = wb.worksheets[0]
            rows = list(ws.iter_rows(values_only=True))
        finally:
            wb.close()
        head = rows[0]
        headers: dict[int, str] = {}
        last = ""
        for i, v in enumerate(head, start=1):
            if v is not None and str(v).strip():
                last = str(v)
            headers[i] = last
        groups: dict[int, str] = {}
        items: list[tuple[Any, ...]] = []
        for r in rows[HEADER_ROWS:]:
            if not any(v is not None and str(v).strip() for v in r):
                continue
            if r[0] is None:  # строка-заголовок группы: номер в «Номер», название в «Группа происшествий»
                if r[4] is not None and r[5]:
                    groups[int(str(r[4]))] = " ".join(str(r[5]).split())
                continue
            items.append(tuple(r))
        return ClassifierSheet(
            file_name=self._path.name, file_sha256=digest, column_headers=headers, group_titles=groups, rows=items
        )


class YamlCuratedSource:
    def __init__(self, directory: Path) -> None:
        self._dir = directory

    def _load(self, name: str) -> Any:
        path = self._dir / name
        if not path.exists():
            raise DomainError(f"Нет файла справочника: {path}", code="source_missing")
        return yaml.safe_load(path.read_text(encoding="utf-8"))

    def read(self) -> CuratedDictionaries:
        enums: dict[str, list[dict[str, Any]]] = self._load("enums.yaml")["enums"]
        channels = self._load("channels.yaml")["channels"]
        return CuratedDictionaries(
            okrugs=self._load("okrugs.yaml")["okrugs"],
            districts=self._load("districts.yaml")["districts"],
            services=self._load("services_core.yaml")["services"] + self._load("services_territorial.yaml")["services"],
            enums=enums,
            channels=channels,
            card_types=self._load("card_types.yaml")["card_types"],
            columns=self._load("classifier_columns.yaml")["columns"],
        )
