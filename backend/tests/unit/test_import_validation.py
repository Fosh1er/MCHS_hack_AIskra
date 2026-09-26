"""Импорт должен падать при изменении раскладки xlsx или ссылках на неизвестные службы/признаки."""

from pathlib import Path

import pytest

from aiskra.modules.dictionaries.application.commands.import_dictionaries import validate_columns
from aiskra.modules.dictionaries.infrastructure.sources import XlsxClassifierSource, YamlCuratedSource
from aiskra.shared.errors import DomainError

DATA = Path(__file__).resolve().parents[3] / "data"


@pytest.fixture(scope="module")
def sheet_and_curated():  # type: ignore[no-untyped-def]
    return XlsxClassifierSource(DATA / "source" / "classifier_v046.xlsx").read(), YamlCuratedSource(
        DATA / "dictionaries"
    ).read()


def test_columns_match_real_file(sheet_and_curated) -> None:  # type: ignore[no-untyped-def]
    sheet, curated = sheet_and_curated
    assert len(validate_columns(sheet, curated)) == 76
    assert len(sheet.rows) == 1281 and len(sheet.group_titles) == 23


def test_layout_change_is_detected(sheet_and_curated) -> None:  # type: ignore[no-untyped-def]
    sheet, curated = sheet_and_curated
    broken = dict(sheet.column_headers)
    broken[55] = "Что-то другое"
    sheet2 = type(sheet)(sheet.file_name, sheet.file_sha256, broken, sheet.group_titles, sheet.rows)
    with pytest.raises(DomainError, match="Колонка 55"):
        validate_columns(sheet2, curated)


def test_unknown_flag_is_rejected(sheet_and_curated) -> None:  # type: ignore[no-untyped-def]
    sheet, curated = sheet_and_curated
    cols = [dict(c) for c in curated.columns]
    cols[1]["flag"] = "no_such_flag"
    curated2 = type(curated)(
        curated.okrugs, curated.districts, curated.services, curated.enums, curated.channels, curated.card_types, cols
    )
    with pytest.raises(DomainError, match="неизвестный признак"):
        validate_columns(sheet, curated2)
