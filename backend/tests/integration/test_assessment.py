"""П. 3.4 через HTTP: учебный вызов → карточка по эталону → оценка 112; работа ДДС → оценка ДДС; инсайты."""

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.integration.test_journal import app_client as journal_app_client  # noqa: F401
from tests.integration.test_journal import as_user


@pytest.fixture(scope="module")
def app_client(journal_app_client: Callable[[], TestClient]) -> Iterator[Callable[[], TestClient]]:  # noqa: F811
    yield journal_app_client


def fill_from_reference(ref: dict[str, Any], aon: str) -> dict[str, Any]:
    a = ref["address"]
    return {
        "phones": {"aon": aon},
        "channel": "mts",
        "applicant": {**ref["applicant"], "foreign_language": False},
        "victims": ref["victims"],
        "card_types": ref["card_types"],
        "incident_types": ref["incident_types"],
        "questionnaire": ref["questionnaire"],
        "card_flags": ref["card_flags"],
        "address": {k: a.get(k) or "" for k in ("street", "house", "building", "structure", "okrug", "district")},
        "description": " ".join(ref["description_keywords"]) + ". Заявитель сообщает о происшествии.",
    }


def test_112_and_dds_assessment(app_client: Callable[[], TestClient]) -> None:
    student = as_user(app_client, "student")
    teacher = as_user(app_client, "teacher")
    call = student.post("/api/v1/training/calls/incoming", json={"groups": [1]}).json()
    ref = teacher.get(f"/api/v1/training/scenarios/{call['scenario_id']}").json()["reference_card"]
    card = student.post("/api/v1/incidents/cards", json={"aon": call["aon"], "scenario_id": call["scenario_id"]}).json()
    student.post(f"/api/v1/training/calls/{call['call_id']}/answer", json={"card_id": card["id"]})
    for q in ("Что случилось?", "Назовите адрес", "Есть пострадавшие?"):
        student.post(f"/api/v1/training/calls/{call['call_id']}/replicas", json={"text": q})
    services = [{"code": s["code"], "is_main": s["main"], "added_by": "auto"} for s in ref["services"]]
    r = student.post(
        f"/api/v1/incidents/cards/{card['id']}/save",
        json={"data": fill_from_reference(ref, call["aon"]), "services": services},
    )
    assert r.status_code == 200, r.text

    res = student.post(f"/api/v1/assessment/cards/{card['id']}/evaluate", json={"role": "112"})
    assert res.status_code == 200, res.text
    a = res.json()
    keys = {c["key"]: c for c in a["details"]["criteria"]}
    assert keys["type"]["score"] == 1 and keys["services"]["score"] == 1 and keys["interview"]["score"] == 1
    assert keys["grammar"]["score"] is None and "не проверено" in keys["grammar"]["note"]
    assert a["score"] >= 90 and a["passed"] and a["grader"] == "rules"
    assert student.get(f"/api/v1/assessment/cards/{card['id']}", params={"role": "112"}).json()["id"] == a["id"]
    other = as_user(app_client, "petrov")
    assert other.post(f"/api/v1/assessment/cards/{card['id']}/evaluate", json={"role": "112"}).status_code == 404

    dds_code = next((s["code"] for s in ref["services"] if s["code"].startswith("DDS_")), ref["services"][0]["code"])
    base = f"/api/v1/incidents/dds/{dds_code}/cards/{card['id']}"
    other.post(f"{base}/received")
    other.post(f"{base}/status", json={"status": "accepted", "order_no": "5", "comment": "Направлена бригада"})
    other.post("/api/v1/training/calls/dds", json={"card_id": card["id"], "service_code": dds_code, "party": "brigade"})
    d = other.post(
        f"/api/v1/assessment/cards/{card['id']}/evaluate", json={"role": "dds", "service_code": dds_code}
    ).json()
    dk = {c["key"]: c for c in d["details"]["criteria"]}
    assert dk["decision"]["score"] == 1 and dk["order_no"]["score"] == 1 and dk["calls"]["score"] == 1
    assert any("Работы завершены" in e for e in dk["chain"]["errors"])

    insights = teacher.get("/api/v1/assessment/insights").json()
    assert insights["assessments"] >= 2 and insights["weakest"]
    assert student.get("/api/v1/assessment/insights").status_code == 403


def test_draft_is_not_assessed(app_client: Callable[[], TestClient]) -> None:
    student = as_user(app_client, "student")
    card = student.post("/api/v1/incidents/cards", json={"aon": ""}).json()
    assert student.post(f"/api/v1/assessment/cards/{card['id']}/evaluate", json={"role": "112"}).status_code == 422
