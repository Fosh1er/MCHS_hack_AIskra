"""Пояснительная записка (п. 7.2) не расходится с системой: матрица покрывает все требования ТЗ,
перечень API — все операции приложения, модель данных — все таблицы."""

import importlib.util
import json
import re
from pathlib import Path

import pytest

BUILD = Path(__file__).resolve().parents[3] / "docs" / "delivery" / "build.py"


@pytest.fixture(scope="module")
def build(tmp_path_factory: pytest.TempPathFactory):
    spec = importlib.util.spec_from_file_location("delivery_build", BUILD)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.OUT = tmp_path_factory.mktemp("delivery")
    return mod


def test_matrix_covers_every_requirement(build) -> None:
    ids = [rid for rid, _, _ in build.requirements()]
    assert len(ids) == 83
    assert set(ids) == set(build.MATRIX), "статус в MATRIX должен быть ровно у требований из 01"
    assert all(status in build.STATUS_WORDS for _, status, _ in build.MATRIX.values())
    md = build.matrix_md()
    assert md.startswith("Итог: реализовано")
    # в матрице — обязательные требования и реализованные желательные и возможные
    shown = [r for r, _, p in build.requirements() if not (p[:1] in ("S", "C") and build.MATRIX[r][1] in ("🟡", "⏳"))]
    assert md.count("\n| ") == len(shown) + 1  # заголовок + строки
    assert all(f"\n| {r} |" in md for r, _, p in build.requirements() if p.startswith("M"))


def test_api_table_lists_every_operation(build) -> None:
    md = build.api_md()
    spec = json.loads((build.OUT / "openapi.json").read_text("utf-8"))
    for path, ops in spec["paths"].items():
        for method in ops:
            assert f"| {method.upper()} | `{path}` |" in md


def test_data_model_lists_every_table(build) -> None:
    from aiskra.platform.models_registry import metadata

    md = build.data_model_md()
    for table in metadata.sorted_tables:
        assert f"| `{table.name}` |" in md


def test_source_placeholders_are_known(build) -> None:
    src = (BUILD.parent / "Пояснительная_записка.md").read_text("utf-8")
    assert set(re.findall(r"\{\{(\w+)\}\}", src)) == {"MATRIX", "DATA_MODEL", "API_TABLE", "LIBRARIES"}


def test_size_tables_keeps_short_codes_unbroken(build) -> None:
    md = "| № | Текст | Статус |\n|---|---|---|\n| 1 | " + "длинный текст " * 10 + " | частично |"
    sep = build.size_tables(md).split("\n")[1]
    widths = [len(c) for c in sep.strip("|").split("|")]
    assert widths[2] >= int(len("частично") * 1.8)
    assert widths[1] == 40
