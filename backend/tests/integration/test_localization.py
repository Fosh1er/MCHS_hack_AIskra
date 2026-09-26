"""П. 6.3: ошибки проверки запроса и HTTP — по-русски и в общем формате {error, message}."""

from fastapi.testclient import TestClient


def test_validation_errors_in_russian(admin: TestClient) -> None:
    r = admin.post("/api/v1/groups", json={"name": "x", "members": [{"user_id": "не-uuid"}], "junk": 1})
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "validation_error" and body["message"].startswith("Проверьте данные")
    by_field = {f["field"]: f["message"] for f in body["fields"]}
    assert by_field["name"] == "не короче 2 символов"
    assert by_field["members.0.user_id"] == "неверный идентификатор"
    assert by_field["junk"] == "лишнее поле"
    assert not any(ch.isascii() and ch.isalpha() for ch in by_field["name"])  # без английского текста


def test_query_and_http_errors_in_russian(admin: TestClient) -> None:
    r = admin.get("/api/v1/audit", params={"page": "abc"})
    assert r.status_code == 422 and r.json()["fields"][0] == {
        "field": "параметр page",
        "message": "ожидается целое число",
    }
    nf = admin.get("/api/v1/no-such-route")
    assert nf.status_code in (401, 404) and nf.json()["message"] in ("Не найдено", "Требуется вход в систему")
    assert admin.delete("/api/v1/auth/me").json()["message"] == "Метод не поддерживается"
