"""П. 3.6 через HTTP: занятие с психологическим модификатором → звонок с профилем → разметка реплик → блок оценки
«Работа с заявителем»; закрепление профиля за сценарием; пауза; права."""

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aiskra.modules.training.infrastructure.psy_catalog import YamlPsyCatalog
from tests.integration.test_assessment import fill_from_reference
from tests.integration.test_journal import app_client as journal_app_client  # noqa: F401
from tests.integration.test_journal import as_user

CATALOG_PATH = Path(__file__).resolve().parents[3] / "data" / "dictionaries" / "psy_profiles.yaml"


@pytest.fixture(scope="module")
def app_client(journal_app_client: Callable[[], TestClient]) -> Iterator[Callable[[], TestClient]]:  # noqa: F811
    yield journal_app_client


def _session(teacher: TestClient, student_id: str, psy: dict[str, object]) -> str:
    body = {
        "title": "Занятие: сложный заявитель",
        "mode": "cards_112",
        "card_source": "generated",
        "groups": [1],
        "participants": [{"student_id": student_id, "role": "112"}],
        "settings": {"psy": psy},
    }
    r = teacher.post("/api/v1/training/sessions", json=body)
    assert r.status_code == 201, r.text
    sid: str = r.json()["id"]
    assert teacher.post(f"/api/v1/training/sessions/{sid}/start").json()["status"] == "running"
    return sid


def test_psy_catalog_and_scenario_profile(app_client: Callable[[], TestClient]) -> None:
    teacher, student = as_user(app_client, "teacher"), as_user(app_client, "student")
    profiles = teacher.get("/api/v1/training/psy/profiles").json()
    ids = {p["id"] for p in profiles}
    assert {"panic", "crying", "aggression", "suicidal"} <= ids
    assert all(p["sources"] for p in profiles)
    assert student.get("/api/v1/training/psy/profiles").status_code == 403

    sid = teacher.post("/api/v1/training/scenarios/generate", json={"count": 1, "groups": [1]}).json()["ids"][0]
    assert (
        teacher.post(f"/api/v1/training/scenarios/{sid}/psy", json={"profile": "crying"}).json()["status"] == "crying"
    )
    assert teacher.get(f"/api/v1/training/scenarios/{sid}").json()["psy_profile"] == "crying"
    bad = teacher.post(f"/api/v1/training/scenarios/{sid}/psy", json={"profile": "ghost"})
    assert bad.status_code == 422 and bad.json()["error"] == "unknown_psy_profile"
    assert student.post(f"/api/v1/training/scenarios/{sid}/psy", json={"profile": "panic"}).status_code == 403
    assert teacher.post(f"/api/v1/training/scenarios/{sid}/psy", json={"profile": None}).json()["status"] == "none"


def test_session_with_modifier_call_and_block(app_client: Callable[[], TestClient]) -> None:
    teacher, student = as_user(app_client, "teacher"), as_user(app_client, "student")
    for sid in teacher.post("/api/v1/training/scenarios/generate", json={"count": 2, "groups": [1]}).json()["ids"]:
        teacher.post(f"/api/v1/training/scenarios/{sid}/approve")
    people = {s["login"]: s["id"] for s in teacher.get("/api/v1/training/students").json()}
    unknown = teacher.post(
        "/api/v1/training/sessions",
        json={
            "title": "Ошибка",
            "mode": "cards_112",
            "participants": [{"student_id": people["student"], "role": "112"}],
            "settings": {"psy": {"enabled": True, "profiles": ["ghost"]}},
        },
    )
    assert unknown.status_code == 422 and unknown.json()["error"] == "bad_psy_setting"
    session_id = _session(teacher, people["student"], {"enabled": True, "share": 1, "profiles": ["panic"]})

    call = student.post("/api/v1/training/calls/incoming", json={"groups": [1]}).json()
    assert call["warning"] is None  # паника — не кризисный профиль
    ref = teacher.get(f"/api/v1/training/scenarios/{call['scenario_id']}").json()["reference_card"]
    card = student.post(
        "/api/v1/incidents/cards",
        json={"aon": call["aon"], "scenario_id": call["scenario_id"], "session_id": session_id},  # для отчёта занятия
    ).json()
    opening = student.post(f"/api/v1/training/calls/{call['call_id']}/answer", json={"card_id": card["id"]}).json()
    assert opening["voice"]["profile"] == "panic" and opening["voice"]["level"] == 4
    say = f"/api/v1/training/calls/{call['call_id']}/replicas"
    r = student.post(say, json={"text": "Успокойтесь! Назовите адрес."}).json()
    assert r["voice"]["level"] == 5 and "[" not in r["text"]  # ремарки — отдельно от озвучиваемого текста
    for text in (
        "Я на линии, помощь уже направляю. Мне нужен адрес, чтобы направить помощь. Назовите адрес.",
        "Мне нужен адрес, чтобы направить помощь. Назовите адрес.",
        "Дышите со мной: медленный вдох и выдох. Назовите адрес.",
        "Мне нужен адрес, чтобы направить помощь. Назовите адрес.",
        "Что случилось?",
        "Есть пострадавшие?",
    ):
        r = student.post(say, json={"text": text, "latency_ms": 1500})
        assert r.status_code == 200, r.text
    view = student.get(f"/api/v1/training/calls/{call['call_id']}").json()
    assert view["psy"]["profile"] == "panic" and view["psy"]["peak"] == 5
    first_op = next(m for m in view["messages"] if m["speaker"] == "operator")
    assert {"CALM_DOWN"} <= {a["code"] for a in first_op["meta"]["acts"]}
    student.post(f"/api/v1/training/calls/{call['call_id']}/end")

    services = [{"code": s["code"], "is_main": s["main"], "added_by": "auto"} for s in ref["services"]]
    saved = student.post(
        f"/api/v1/incidents/cards/{card['id']}/save",
        json={"data": fill_from_reference(ref, call["aon"]), "services": services},
    )
    assert saved.status_code == 200, saved.text
    a = student.post(f"/api/v1/assessment/cards/{card['id']}/evaluate", json={"role": "112"}).json()
    psy = a["details"]["psy"]
    keys = {c["key"]: c for c in psy["criteria"]}
    assert keys["psy_forbidden"]["score"] < 1 and any(
        "успокойтесь" in e.lower() for e in keys["psy_forbidden"]["errors"]
    )
    assert keys["psy_judge"]["score"] is None and keys["psy_voice"]["score"] is not None  # голосовой канал был
    assert psy["weight"] == 0 and a["score"] == a["details"]["role_score"]  # вес 0 — блок отдельно от итога
    assert psy["timeline"][0]["speaker"] in {"party", "operator"} and psy["stats"]["start"] == 4
    # F4, RF4-02: у критерия — «почему» и источники, у ✗ в ленте — источник
    assert keys["psy_forbidden"]["why"] and {s["source"] for s in keys["psy_forbidden"]["sources"]} >= {"РФ-1"}
    bad = [a for t in psy["timeline"] for a in t.get("acts") or [] if not a["good"]]
    assert bad and all(a["sources"] for a in bad)
    # F4, RF4-05: сводка по группе в отчёте занятия
    report = teacher.get(f"/api/v1/assessment/sessions/{session_id}/report").json()
    top = {e["code"]: e for e in report["psy_errors"]["items"]}
    assert report["psy_errors"]["calls"] == 1 and top["CALM_DOWN"]["students"] == 1
    assert top["CALM_DOWN"]["sources"] and top["CALM_DOWN"]["title"]
    teacher.post(f"/api/v1/training/sessions/{session_id}/finish")


def test_pause_and_sensitive_warning(app_client: Callable[[], TestClient]) -> None:
    teacher, student = as_user(app_client, "teacher"), as_user(app_client, "student")
    # D4: сценарий с кризисным профилем — в своей группе классификатора (2, остальные тесты модуля — в группе 1).
    # Раньше он лежал в общей группе 1: вызов выбирал его из банка случайно (12 попыток, ≈1 % промахов), а в другом
    # порядке тестов закреплённый «suicidal» попадал в звонок соседнего теста и ломал его.
    sid = teacher.post("/api/v1/training/scenarios/generate", json={"count": 1, "groups": [2]}).json()["ids"][0]
    teacher.post(f"/api/v1/training/scenarios/{sid}/approve")
    teacher.post(f"/api/v1/training/scenarios/{sid}/psy", json={"profile": "suicidal"})
    people = {s["login"]: s["id"] for s in teacher.get("/api/v1/training/students").json()}
    session_id = _session(teacher, people["student"], {"enabled": True, "share": 0, "sensitive": ["suicidal"]})
    warned = student.post("/api/v1/training/calls/incoming", json={"groups": [2]}).json()
    assert warned["scenario_id"] == sid  # в группе 2 утверждённый сценарий один
    assert warned["warning"] and "отказаться" in warned["warning"]
    paused = student.post(f"/api/v1/training/calls/{warned['call_id']}/pause")
    assert paused.status_code == 200 and paused.json()["status"] == "ended"
    view = student.get(f"/api/v1/training/calls/{warned['call_id']}").json()
    assert view["psy"]["paused"] is True
    admin = as_user(app_client, "admin")
    events = {e["event"] for e in admin.get("/api/v1/audit", params={"page_size": 100}).json()["items"]}
    assert "calls.paused" in events
    teacher.post(f"/api/v1/training/sessions/{session_id}/finish")


def test_methodology_matches_catalog(app_client: Callable[[], TestClient]) -> None:
    """F4, RF4-03: страница «Методика» собирается из каталога — все профили и их источники, расхождений нет."""
    catalog = YamlPsyCatalog(CATALOG_PATH)
    for role in ("student", "teacher"):
        m = as_user(app_client, role).get("/api/v1/training/psy/methodology")
        assert m.status_code == 200, m.text
    data = m.json()
    profiles = {p["id"]: p for p in data["profiles"]}
    assert set(profiles) == set(catalog.profiles())
    for pid, p in catalog.profiles().items():
        card = profiles[pid]
        assert card["title"] == p.title and card["sources"] == list(p.sources)
        assert {a["code"] for a in card["does"]} == set(p.helps) | set(p.key_acts)
        assert {a["code"] for a in card["donts"] if a["critical"]} == set(p.critical)
        assert all(code in data["sources"] for code in card["sources"])
    basis = [b["source"]["code"] for b in data["basis"]]
    assert {"РФ-1", "РФ-2", "РФ-13", "РФ-6", "РФ-10", "М-0.1", "М-1.1"} <= set(basis)
    assert all(b["source"]["official"] for b in data["basis"])
    assert [lv["level"] for lv in data["scale"]] == [1, 2, 3, 4, 5]


def test_psy_basis_and_scenario_filter(app_client: Callable[[], TestClient]) -> None:
    teacher, student = as_user(app_client, "teacher"), as_user(app_client, "student")
    basis = student.get("/api/v1/assessment/psy/basis").json()
    assert {c["key"] for c in basis["criteria"]} >= {"psy_forbidden", "psy_outcome"}
    assert all(c["why"] and c["sources"] for c in basis["criteria"] + basis["acts"])

    sid = teacher.post("/api/v1/training/scenarios/generate", json={"count": 1, "groups": [1]}).json()["ids"][0]
    teacher.post(f"/api/v1/training/scenarios/{sid}/psy", json={"profile": "aggression"})
    with_psy = teacher.get("/api/v1/training/scenarios", params={"status": "", "psy": "any", "page_size": 100}).json()
    assert sid in {s["id"] for s in with_psy["items"]} and all(s["psy_profile"] for s in with_psy["items"])
    exact = teacher.get("/api/v1/training/scenarios", params={"psy": "aggression", "page_size": 100}).json()
    assert {s["psy_profile"] for s in exact["items"]} == {"aggression"}
    without = teacher.get("/api/v1/training/scenarios", params={"psy": "none", "page_size": 100}).json()
    assert sid not in {s["id"] for s in without["items"]} and not any(s["psy_profile"] for s in without["items"])
