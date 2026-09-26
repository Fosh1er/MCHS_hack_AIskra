"""RBAC через HTTP: запрет по умолчанию, права ролей, отказ в доступе пишется в аудит."""

from collections.abc import Callable
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tests.integration.conftest import login

PUBLIC = {("POST", "/api/v1/auth/login")}


def test_every_api_route_requires_session(client: TestClient) -> None:
    """Запрет по умолчанию: новый эндпоинт без входа недоступен, даже если автор забыл require(...).
    Маршруты берутся из OpenAPI-схемы — это полный список того, что приложение отдаёт наружу."""
    checked = 0
    for template, operations in client.get("/openapi.json").json()["paths"].items():
        if not template.startswith("/api/v1"):
            continue
        path = template.replace("{user_id}", str(uuid4())).replace("{code}", "101").replace("{domain}", "channel")
        for method in operations:
            if (method.upper(), template) in PUBLIC:
                continue
            r = client.request(method.upper(), path, json={})
            assert r.status_code == 401, f"{method.upper()} {template} → {r.status_code}"
            checked += 1
    assert checked >= 15


@pytest.mark.parametrize(
    ("user", "method", "path", "expected"),
    [
        ("student", "GET", "/api/v1/dictionaries/card-types", 200),
        ("student", "GET", "/api/v1/audit", 403),
        ("student", "GET", "/api/v1/system/ai", 403),
        ("student", "GET", "/api/v1/users", 403),
        ("teacher", "GET", "/api/v1/dictionaries/card-types", 200),
        ("teacher", "GET", "/api/v1/users", 403),
        ("teacher", "GET", "/api/v1/audit", 403),
        ("teacher", "POST", "/api/v1/dictionaries/import", 403),
        ("admin", "GET", "/api/v1/audit", 200),
        ("admin", "GET", "/api/v1/users", 200),
        ("admin", "GET", "/api/v1/system/ai", 200),
    ],
)
def test_role_permissions(client: TestClient, user: str, method: str, path: str, expected: int) -> None:
    login(client, user)
    r = client.request(method, path)
    assert r.status_code == expected, r.text
    if expected == 403:
        assert r.json()["error"] == "permission_denied"


def test_access_denied_is_audited(app_client: Callable[[], TestClient], admin: TestClient) -> None:
    student = app_client()
    login(student, "student")
    assert student.get("/api/v1/audit").status_code == 403
    denied = admin.get("/api/v1/audit", params={"event": "auth.access_denied"}).json()["items"]
    assert denied[0]["actor_login"] == "student"
    assert denied[0]["description"] == "GET /api/v1/audit: нет права «audit.read»"
    assert denied[0]["arm_number"] == "123" and denied[0]["operator_number"] == "7"


def test_role_change_applies_on_next_request(app_client: Callable[[], TestClient], admin: TestClient) -> None:
    teacher = app_client()
    login(teacher, "teacher")
    assert teacher.get("/api/v1/audit").status_code == 403
    teacher_id = teacher.get("/api/v1/auth/me").json()["user_id"]
    r = admin.patch(f"/api/v1/users/{teacher_id}", json={"role": "admin"})
    assert r.json() == {"changed": ["роль"]}
    assert teacher.get("/api/v1/audit").status_code == 200  # без повторного входа
