"""П. 3.3: разделы эталона — отпечатки, сброс решения после правки, сценарии, утверждённые целиком до разделов."""

from aiskra.modules.training.domain.review import Decision, all_accepted, mark_sections, review_state
from aiskra.modules.training.domain.scenario import Scenario, ScenarioStatus


def scenario(status: ScenarioStatus = ScenarioStatus.DRAFT) -> Scenario:
    return Scenario(
        title="Пожар в квартире",
        difficulty=2,
        card_type_code="101",
        incident_type_code="1050001",
        legend={"opening": "Алло, горим!", "what": "пожар", "applicant": {"name": "Иванова"}},
        reference_card={"final_type": "Пожар", "services": [{"code": "S101", "main": True}]},
        reference_dds={"first_status": "accepted"},
        status=status,
    )


def decisions(s: Scenario) -> list[str | None]:
    return [r.decision for r in review_state(s)]


def test_edit_resets_only_changed_section() -> None:
    s = scenario()
    mark_sections(
        s, {k: (Decision.ACCEPTED, "") for k in ("story", "applicant", "classification", "services", "dds")}, by="t"
    )
    assert all_accepted(s)
    s.legend["opening"] = "Алло! Помогите!"
    state = {r.key: r for r in review_state(s)}
    assert state["story"].decision is None and state["story"].stale
    assert state["services"].decision == "accepted" and not all_accepted(s)


def test_approved_before_sections_counts_as_accepted_and_keeps_them() -> None:
    s = scenario(ScenarioStatus.APPROVED)  # утверждён целиком: засев стенда или данные до п. 3.3
    assert decisions(s) == ["accepted"] * 5
    mark_sections(s, {"dds": (Decision.REWORK, "нужен звонок старшему")}, by="t")
    s.status = ScenarioStatus.DRAFT  # так делает обработчик: раздел на доработке снимает утверждение
    assert decisions(s) == ["accepted"] * 4 + ["rework"]
