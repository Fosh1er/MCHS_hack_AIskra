"""П. 4.4: определение типа файла, выдержки, поиск выдержек, выдержки в промпте генерации."""

import asyncio
from typing import Any

import pytest

from aiskra.modules.training.application.commands.scenarios import ScenarioGenerator
from aiskra.modules.training.domain.material import FileType, best_passages, detect_type, passages, safe_filename
from aiskra.shared.errors import DomainError
from tests.materials_samples import docx, pdf


def test_detect_type_by_content() -> None:
    assert detect_type("a.pdf", pdf("x")[:16]) is FileType.PDF
    assert detect_type("renamed.txt", b"%PDF-1.7") is FileType.PDF  # сигнатура важнее расширения
    assert detect_type("a.docx", docx(["x"])[:8]) is FileType.DOCX
    assert detect_type("памятка.md", "Пожар: звонить 112".encode()) is FileType.TEXT
    with pytest.raises(DomainError):
        detect_type("virus.pdf", b"MZ\x90\x00")  # исполняемый файл под видом PDF
    with pytest.raises(DomainError):
        detect_type("a.zip", b"PK\x03\x04")
    with pytest.raises(DomainError):
        detect_type("cp1251.txt", "Пожар".encode("cp1251") + b"xxxx")


def test_passages_and_search() -> None:
    text = "Пожар в квартире: уточнить этаж и наличие людей.\n\nДТП: число машин и пострадавших.\n\n" + "Газ. " * 300
    ps = passages(text, size=200)
    assert ps[0].startswith("Пожар") and all(len(p) <= 200 for p in ps)
    found = best_passages("пожара в квартирах", [("Памятка", text)], limit=2)
    assert found and found[0][0] == "Памятка" and "Пожар" in found[0][1]
    assert best_passages("вертолёт", [("Памятка", text)]) == []
    assert safe_filename("../../etc/pass wd?.pdf") == "pass wd_.pdf"


class _Ctx:
    async def snippets(self, query: str, limit: int = 3) -> list[tuple[str, str]]:
        return [("Инструкция", f"по запросу: {query}")]


def test_generation_facts_get_material_snippets() -> None:
    gen = ScenarioGenerator(facts=None, router=None, materials=_Ctx())  # type: ignore[arg-type]
    facts: dict[str, Any] = {"тип": "Пожар в квартире", "признаки": ["Дом", "Квартира", None]}
    out = asyncio.run(gen._with_materials(facts))
    assert out["выдержки_из_учебных_материалов"] == ["Инструкция: по запросу: Пожар в квартире Дом Квартира"]
    assert asyncio.run(ScenarioGenerator(None, None)._with_materials(facts)) == facts  # type: ignore[arg-type]
