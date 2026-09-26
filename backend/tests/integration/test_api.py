from fastapi.testclient import TestClient


def test_health_is_public(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["db"] == "ok"
    assert body["ai"]["allow_external"] is False


def test_ai_config_query(admin: TestClient) -> None:
    body = admin.get("/api/v1/system/ai").json()
    assert body["default_provider"] == "fake"


def test_probe_command_second_call_is_cached(admin: TestClient) -> None:
    first = admin.post("/api/v1/system/ai/probe", json={"prompt": "Скажи «готов»"}).json()
    second = admin.post("/api/v1/system/ai/probe", json={"prompt": "Скажи «готов»"}).json()
    assert first["provider"] == "fake" and first["cached"] is False
    assert second["cached"] is True and second["text"] == first["text"]
    assert admin.get("/health").json()["ai"]["cache"]["hits"] >= 1


def test_domain_error_maps_to_422(admin: TestClient) -> None:
    r = admin.post("/api/v1/system/ai/probe", json={"prompt": "   "})
    assert r.status_code == 422 and r.json()["error"] == "empty_prompt"


def test_openapi_available(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/api/v1/system/ai/probe", "/api/v1/auth/login", "/api/v1/audit"} <= set(paths)
