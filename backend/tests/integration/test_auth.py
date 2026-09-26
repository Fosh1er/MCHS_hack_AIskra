"""П. 0.3 через HTTP: вход с номером АРМ, cookie-сессия, выход, защита от подбора, блокировка."""

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from tests.integration.conftest import PASSWORD, login


def audit(admin: TestClient, **params: Any) -> list[dict[str, Any]]:
    r = admin.get("/api/v1/audit", params={"page_size": 100, **params})
    assert r.status_code == 200, r.text
    items: list[dict[str, Any]] = r.json()["items"]
    return items


def test_login_sets_httponly_strict_cookie_and_returns_role(client: TestClient) -> None:
    r = client.post("/api/v1/auth/login", json={"login": "Admin", "password": PASSWORD, "arm_number": "123"})
    assert r.status_code == 200, r.text
    cookie = r.headers["set-cookie"].lower()
    assert "aiskra_session=" in cookie and "httponly" in cookie and "samesite=strict" in cookie and "path=/" in cookie
    body = r.json()
    assert (body["login"], body["role"], body["role_title"], body["arm_number"]) == (
        "admin",
        "admin",
        "Администратор",
        "123",
    )
    assert "audit.read" in body["permissions"] and "expires_at" in body
    me = client.get("/api/v1/auth/me").json()
    assert me["user_id"] == body["user_id"] and me["arm_number"] == "123"


def test_wrong_credentials_are_generic_401_and_audited(client: TestClient, admin: TestClient) -> None:
    for user, password in [("student", "wrong-password"), ("ghost", PASSWORD)]:
        r = client.post("/api/v1/auth/login", json={"login": user, "password": password})
        assert r.status_code == 401
        assert r.json() == {"error": "unauthenticated", "message": "Неверный логин или пароль"}
    failed = audit(admin, event="auth.login_failed")
    assert {(e["actor_login"], e["description"]) for e in failed} == {
        ("student", "Неверный пароль"),
        ("ghost", "Неизвестный логин"),
    }


def test_bad_arm_number_is_422(client: TestClient) -> None:
    r = client.post("/api/v1/auth/login", json={"login": "student", "password": PASSWORD, "arm_number": "12a"})
    assert r.status_code == 422 and r.json()["error"] == "bad_number"


def test_bruteforce_lockout(client: TestClient, admin: TestClient) -> None:
    for _ in range(3):  # login_max_attempts=3 в тестовых настройках
        assert client.post("/api/v1/auth/login", json={"login": "teacher", "password": "nope-nope"}).status_code == 401
    r = client.post("/api/v1/auth/login", json={"login": "teacher", "password": PASSWORD})
    assert r.status_code == 401 and r.json()["error"] == "account_locked"
    assert audit(admin, event="auth.account_locked")[0]["actor_login"] == "teacher"
    users = admin.get("/api/v1/users", params={"q": "teacher"}).json()["items"]
    assert users[0]["locked_until"] is not None


def test_logout_revokes_session_server_side(client: TestClient) -> None:
    login(client, "student")
    token = client.cookies.get("aiskra_session")
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401
    client.cookies.set("aiskra_session", token or "")  # украденный или сохранённый токен после выхода
    assert client.get("/api/v1/auth/me").json()["error"] == "unauthenticated"


def test_blocking_kills_active_session_immediately(app_client: Callable[[], TestClient], admin: TestClient) -> None:
    student = app_client()
    login(student, "student")
    student_id = student.get("/api/v1/auth/me").json()["user_id"]

    assert admin.post(f"/api/v1/users/{student_id}/block", json={"reason": "тест"}).status_code == 204
    assert student.get("/api/v1/auth/me").status_code == 401
    r = student.post("/api/v1/auth/login", json={"login": "student", "password": PASSWORD})
    assert r.status_code == 401 and r.json()["error"] == "account_blocked"

    assert admin.post(f"/api/v1/users/{student_id}/unblock").status_code == 204
    login(student, "student")
    events = [e["event"] for e in audit(admin, q="student")]
    assert {"users.blocked", "users.unblocked", "auth.login_failed", "auth.login_succeeded"} <= set(events)
