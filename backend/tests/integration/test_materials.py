"""П. 4.4 через HTTP: загрузка PDF/DOCX/XLSX/TXT, права, поиск, просмотр, правка, удаление, аудит."""

from collections.abc import Callable

from fastapi.testclient import TestClient

from tests.integration.conftest import login
from tests.materials_samples import docx, pdf, xlsx


def as_(make: Callable[[], TestClient], user: str) -> TestClient:
    c = make()
    login(c, user)
    return c


def upload(c: TestClient, name: str, data: bytes, **form: str) -> dict:
    r = c.post("/api/v1/training/materials", files={"file": (name, data)}, data={"title": name, **form})
    return {"status": r.status_code, **r.json()}


def test_materials_flow(app_client: Callable[[], TestClient], admin: TestClient) -> None:
    teacher, student = as_(app_client, "teacher"), as_(app_client, "student")
    instr = docx(["Инструкция по заведению карточки 112.", "Пожар в квартире: уточнить этаж, подъезд и наличие людей."])
    r = upload(teacher, "Инструкция.docx", instr, kind="instruction", use_in_prompts="true")
    assert r["status"] == 201, r
    iid = r["id"]
    assert upload(teacher, "copy.docx", instr)["error"] == "duplicate_material"
    assert upload(teacher, "evil.pdf", b"MZ\x90\x00" * 100)["error"] == "bad_file_type"
    assert upload(teacher, "broken.docx", b"PK\x03\x04garbage")["error"] == "unreadable_file"
    assert upload(student, "x.txt", b"hello world text")["status"] == 403
    pid = upload(admin, "Memo.pdf", pdf("Gas leak: evacuate people"), kind="memo")["id"]  # администратор тоже может
    xid = upload(
        teacher,
        "Классификатор.xlsx",
        xlsx([["Код", "Тип"], ["11020100", "Неизвестный запах"]]),
        kind="classifier",
        visible="false",
    )["id"]
    upload(teacher, "Памятка ДДС.md", "Норматив решения ДДС — 30 секунд.".encode(), kind="memo")

    mine = {m["title"]: m for m in teacher.get("/api/v1/training/materials").json()}
    assert (
        len(mine) == 4 and mine["Классификатор.xlsx"]["visible"] is False and mine["Инструкция.docx"]["text_chars"] > 50
    )
    seen = {m["title"] for m in student.get("/api/v1/training/materials").json()}
    assert "Классификатор.xlsx" not in seen and "Инструкция.docx" in seen  # скрытое — только преподавателю
    assert student.get(f"/api/v1/training/materials/{xid}").status_code == 404
    assert [m["title"] for m in student.get("/api/v1/training/materials", params={"q": "подъезд"}).json()] == [
        "Инструкция.docx"
    ]

    view = student.get(f"/api/v1/training/materials/{iid}", params={"q": "пожар в квартире"}).json()
    assert view["file_type"] == "docx" and "подъезд" in view["found"][0]
    assert "Неизвестный запах" in teacher.get(f"/api/v1/training/materials/{xid}").json()["text"]
    assert "Gas leak" in teacher.get(f"/api/v1/training/materials/{pid}").json()["text"]
    f = student.get(f"/api/v1/training/materials/{pid}/file")
    assert (
        f.status_code == 200 and f.content.startswith(b"%PDF") and f.headers["content-disposition"].startswith("inline")
    )
    d = student.get(f"/api/v1/training/materials/{iid}/file")
    assert d.headers["content-disposition"].startswith("attachment")

    assert (
        teacher.patch(
            f"/api/v1/training/materials/{xid}", json={"visible": True, "title": "Классификатор v046"}
        ).status_code
        == 200
    )
    assert "Классификатор v046" in {m["title"] for m in student.get("/api/v1/training/materials").json()}
    assert student.patch(f"/api/v1/training/materials/{xid}", json={"visible": False}).status_code == 403
    assert teacher.delete(f"/api/v1/training/materials/{pid}").status_code == 204
    assert teacher.get(f"/api/v1/training/materials/{pid}").status_code == 404
    events = {e["event"] for e in admin.get("/api/v1/audit", params={"page_size": 100}).json()["items"]}
    assert {"materials.uploaded", "materials.updated", "materials.deleted"} <= events
