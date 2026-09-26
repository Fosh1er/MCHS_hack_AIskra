"""Управление учётными записями (администратор) и поиск по журналу аудита как в АРМ-112."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.integration.conftest import login


def test_create_list_reset_password(app_client: Callable[[], TestClient], admin: TestClient) -> None:
    body = {"login": "Sidorov", "full_name": "Сидоров С. С.", "role": "student", "password": "Student-2026"}
    r = admin.post("/api/v1/users", json=body)
    assert r.status_code == 201 and r.json()["login"] == "sidorov"
    user_id = r.json()["id"]

    assert admin.post("/api/v1/users", json=body).json()["error"] == "login_taken"
    weak = admin.post("/api/v1/users", json={**body, "login": "petrov", "password": "123"})
    assert weak.status_code == 422 and weak.json()["error"] == "weak_password"

    page = admin.get("/api/v1/users", params={"q": "СИДОРОВ"}).json()  # регистр не важен и для кириллицы
    assert page["total"] == 1 and page["items"][0]["role"] == "student"
    assert admin.get("/api/v1/users", params={"role": "admin"}).json()["total"] == 1

    assert admin.post(f"/api/v1/users/{user_id}/password", json={"new_password": "Changed-2026"}).status_code == 204
    sidorov = app_client()
    login(sidorov, "sidorov", password="Changed-2026")


def test_admin_cannot_lock_themselves_out(admin: TestClient) -> None:
    me = admin.get("/api/v1/auth/me").json()["user_id"]
    assert admin.post(f"/api/v1/users/{me}/block", json={}).json()["error"] == "self_block"
    assert admin.patch(f"/api/v1/users/{me}", json={"role": "teacher"}).json()["error"] == "last_admin"
    assert admin.patch("/api/v1/users/00000000-0000-0000-0000-000000000000", json={}).status_code == 404


def test_audit_search_like_original(app_client: Callable[[], TestClient], admin: TestClient) -> None:
    student = app_client()
    login(student, "student")
    student.post("/api/v1/auth/logout")

    by_operator = admin.get("/api/v1/audit", params={"q": "ОБУЧАЮЩИЙСЯ", "by_operator": True}).json()
    assert {i["event_title"] for i in by_operator["items"]} >= {"Вход в систему", "Выход из системы"}
    row = by_operator["items"][0]
    assert set(row) >= {"card_number", "operator_number", "actor_name", "at", "event_title", "description"}

    # без «по оператору» ищется только описание: остаётся создание учётки (логин есть в описании)
    only_description = admin.get("/api/v1/audit", params={"q": "student", "by_operator": False}).json()
    assert {i["event"] for i in only_description["items"]} == {"users.created"}

    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    assert admin.get("/api/v1/audit", params={"date_from": future}).json()["total"] == 0

    first = admin.get("/api/v1/audit").json()
    assert first["page_size"] == 15 and first["page"] == 1 and first["total"] >= 3
    assert first["items"] == sorted(first["items"], key=lambda i: i["at"], reverse=True)

    types = admin.get("/api/v1/audit/event-types").json()
    assert {"code": "auth.logout", "title": "Выход из системы"} in types
    assert admin.get("/api/v1/audit", params={"page_size": 7}).json()["error"] == "bad_page_size"


def test_audit_is_append_only(admin: TestClient) -> None:
    paths = admin.get("/openapi.json").json()["paths"]
    mutating = {(path, m) for path, ops in paths.items() if path.startswith("/api/v1/audit") for m in ops if m != "get"}
    # единственное изменение журнала — очистка по сроку хранения (≥183 дн., п. 6.2); отдельную запись не удалить
    assert mutating == {("/api/v1/audit/purge", "post")}
