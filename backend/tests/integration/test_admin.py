"""П. 5.2 через HTTP: группы, настройки и их применение к занятию, состояние сервисов, логи, резервная копия."""

from collections.abc import Callable

from fastapi.testclient import TestClient

from tests.integration.conftest import login


def as_(make: Callable[[], TestClient], user: str) -> TestClient:
    c = make()
    login(c, user)
    return c


def test_groups_crud_and_access(app_client: Callable[[], TestClient], admin: TestClient) -> None:
    teacher, student = as_(app_client, "teacher"), as_(app_client, "student")
    users = {u["login"]: u["id"] for u in admin.get("/api/v1/users").json()["items"]}
    body = {
        "name": "Группа 112-1",
        "members": [{"user_id": users["student"], "member_role": "dds", "dds_service_code": "S101"}],
    }
    r = admin.post("/api/v1/groups", json=body)
    assert r.status_code == 201, r.text
    gid = r.json()["id"]
    assert admin.post("/api/v1/groups", json=body).json()["error"] == "group_exists"
    bad = {"name": "Другая", "members": [{"user_id": users["teacher"]}]}
    assert admin.post("/api/v1/groups", json=bad).json()["error"] == "not_students"
    no_service = {"name": "Третья", "members": [{"user_id": users["student"], "member_role": "dds"}]}
    assert admin.post("/api/v1/groups", json=no_service).json()["error"] == "service_required"

    groups = teacher.get("/api/v1/groups").json()  # преподаватель читает — назначает занятие группой
    g = next(x for x in groups if x["id"] == gid)
    assert g["members"][0]["full_name"] == "Обучающийся Тестовый" and g["members"][0]["dds_service_code"] == "S101"
    assert teacher.post("/api/v1/groups", json={"name": "x" * 5}).status_code == 403
    assert student.get("/api/v1/groups").status_code == 403

    r = admin.put(f"/api/v1/groups/{gid}", json={"name": "Группа 112-1 (весна)", "members": []})
    assert r.status_code == 200
    assert admin.get("/api/v1/groups").json()[0]["members"] == []
    assert admin.delete(f"/api/v1/groups/{gid}").status_code == 204
    assert admin.get("/api/v1/groups").json() == []
    events = {e["event"] for e in admin.get("/api/v1/audit", params={"page_size": 100}).json()["items"]}
    assert {"groups.created", "groups.updated", "groups.deleted"} <= events


def test_settings_apply_to_sessions(app_client: Callable[[], TestClient], admin: TestClient) -> None:
    teacher = as_(app_client, "teacher")
    s = admin.get("/api/v1/system/settings").json()
    assert s["session_defaults"]["norm_dds"] == 30 and s["backup"]["keep"] == 10
    assert admin.put("/api/v1/system/settings/session_defaults", json={"values": {"norm_dds": 1}}).status_code == 422
    assert admin.put("/api/v1/system/settings/unknown", json={"values": {}}).json()["error"] == "bad_settings_key"
    r = admin.put("/api/v1/system/settings/session_defaults", json={"values": {"norm_dds": 45, "threshold": 60}})
    assert r.status_code == 200 and r.json()["norm_dds"] == 45
    assert teacher.put("/api/v1/system/settings/backup", json={"values": {"keep": 3}}).status_code == 403

    defaults = teacher.get("/api/v1/training/session-defaults").json()
    assert defaults["norm_dds"] == 45 and defaults["threshold"] == 60 and defaults["norm_112"] == 75
    student_id = next(u["id"] for u in admin.get("/api/v1/users").json()["items"] if u["login"] == "student")
    body = {
        "title": "По умолчанию",
        "mode": "cards_112",
        "participants": [{"student_id": student_id, "role": "112"}],
        "settings": {"norm_112": 100},
    }
    sid = teacher.post("/api/v1/training/sessions", json=body).json()["id"]
    got = teacher.get(f"/api/v1/training/sessions/{sid}").json()["settings"]
    assert got["norm_dds"] == 45 and got["threshold"] == 60 and got["norm_112"] == 100  # явное — сильнее
    events = [e for e in admin.get("/api/v1/audit", params={"event": "system.settings_changed"}).json()["items"]]
    assert "norm_dds: 30 → 45" in events[0]["description"]


def test_status_logs_backup_restore(app_client: Callable[[], TestClient], admin: TestClient) -> None:
    status = {x["name"]: x for x in admin.get("/api/v1/system/status").json()}
    assert status["База данных"]["state"] == "ok" and status["Телефония"]["state"] == "ok"
    assert any(n.startswith("ИИ") for n in status) and status["Резервные копии"]["state"] == "warn"
    assert as_(app_client, "teacher").get("/api/v1/system/status").status_code == 403

    admin.get("/api/v1/users")
    logs = admin.get("/api/v1/system/logs", params={"level": "INFO", "limit": 50})
    assert logs.status_code == 200 and isinstance(logs.json(), list)
    assert admin.get("/api/v1/system/logs", params={"level": "LOUD"}).status_code == 422

    b = admin.post("/api/v1/system/backups")
    assert b.status_code == 201, b.text
    info = b.json()
    assert info["rows"] > 0 and info["name"].endswith(".json.gz")
    assert [x["name"] for x in admin.get("/api/v1/system/backups").json()] == [info["name"]]
    file = admin.get(f"/api/v1/system/backups/{info['name']}")
    assert file.status_code == 200 and file.content[:2] == b"\x1f\x8b"  # gzip
    assert admin.get("/api/v1/system/backups/..%2Fsecret").status_code == 404

    # после копии — новый пользователь; восстановление его убирает
    admin.post(
        "/api/v1/users",
        json={
            "login": "tmpuser",
            "full_name": "Временный Пользователь",
            "role": "student",
            "password": "Tmp-Pass-2026x",
        },
    )
    assert admin.post(f"/api/v1/system/backups/{info['name']}/restore", json={"confirm": "да"}).status_code == 422
    r = admin.post(f"/api/v1/system/backups/{info['name']}/restore", json={"confirm": "ВОССТАНОВИТЬ"})
    assert r.status_code == 200, r.text
    assert admin.get("/api/v1/users").status_code == 401  # все сессии завершены
    again = as_(app_client, "admin")
    logins = {u["login"] for u in again.get("/api/v1/users").json()["items"]}
    assert "tmpuser" not in logins and {"admin", "teacher", "student"} <= logins
    events = {e["event"] for e in again.get("/api/v1/audit", params={"page_size": 100}).json()["items"]}
    assert "system.backup_restored" in events
