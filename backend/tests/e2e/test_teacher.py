"""F6.5 п. 1 — преподаватель: генерация сценария моделью → частичное и полное утверждение; занятие с психологическим
профилем и ветвлением (F5) → звонок обучающегося → мониторинг → отчёт → черновик отзыва и сохранение → допуск."""

from __future__ import annotations

import re
from typing import Any

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import Session, Stand
from tests.e2e.helpers import fill_card, finish_running_sessions, party_replies, reference, save_card, say, take_call

pytestmark = pytest.mark.e2e


def _group(code: str | None) -> int | None:
    return int(code[:-6]) if code and len(code) > 6 else None


def test_generate_and_review_scenarios(ui: Session) -> None:
    stand = ui.stand
    teacher = stand.client("teacher")
    page = ui.new_page("teacher")
    page.goto(f"{stand.web}/teacher/scenarios")

    page.get_by_label("Количество").fill("2")
    with page.expect_response(lambda r: r.url.endswith("/training/scenarios/generate")) as gen:
        page.get_by_role("button", name="сгенерировать").click()
    assert gen.value.ok, gen.value.text()
    ids: list[str] = gen.value.json()["ids"]
    expect(page.get_by_text("Создано черновиков: 2")).to_be_visible()
    drafts = {s["id"]: s for s in teacher.get("/training/scenarios", params={"status": "draft"}).json()["items"]}
    assert set(ids) <= set(drafts)
    assert {drafts[i]["source"] for i in ids} == {"ai"}  # легенду написала модель (заглушка), а не шаблон

    # частичное утверждение: один раздел эталона — на доработку с комментарием, остальные приняты
    partial, full = (drafts[i] for i in ids)
    page.locator("tr", has_text=partial["title"]).first.click()
    review = page.locator("[data-tour=t-review]")
    sections = review.locator("ol.tch-review > li")
    expect(sections.first).to_be_visible()
    n = sections.count()
    assert n >= 2
    first_title = sections.first.locator(".tch-review__head span").first.inner_text()
    sections.first.get_by_role("button", name="на доработку").click()
    sections.first.get_by_placeholder("Что доработать").fill("Уточнить подъезд и этаж")
    for i in range(1, n):
        sections.nth(i).get_by_role("button", name="принять").click()
    review.get_by_role("button", name="сохранить решение по разделам").click()
    expect(review.get_by_text(f"Принято разделов: {n - 1} из {n}. Сценарий остаётся на проверке.")).to_be_visible()
    expect(page.locator("tr", has_text=partial["title"]).first).to_contain_text(f"принято {n - 1} из {n}")
    assert teacher.get(f"/training/scenarios/{partial['id']}").json()["status"] == "draft"

    # доработанный раздел принят — сценарий утверждён
    sections.first.get_by_role("button", name="принять").click()
    review.get_by_role("button", name="сохранить решение по разделам").click()
    expect(review.get_by_text("Все разделы приняты — сценарий утверждён")).to_be_visible()
    assert teacher.get(f"/training/scenarios/{partial['id']}").json()["status"] == "approved", first_title

    # полное утверждение кнопкой «утвердить»
    page.locator("tr", has_text=full["title"]).first.click()
    page.get_by_role("button", name="утвердить").click()
    expect(page.get_by_role("button", name="утвердить")).to_have_count(0)
    assert teacher.get(f"/training/scenarios/{full['id']}").json()["status"] == "approved"


def _branching_group(stand: Stand) -> int:
    """Группа классификатора, где в банке только ветвящиеся сценарии: обычные той же группы — в архив.
    Тогда вызов занятия гарантированно ветвящийся (сценарий выбирается случайно из группы)."""
    teacher = stand.client("teacher")
    rows: list[dict[str, Any]] = teacher.get(
        "/training/scenarios", params={"status": "approved", "page_size": 100}
    ).json()["items"]
    branched = [r for r in rows if r.get("branching")]
    assert branched, "в банке нет ветвящихся сценариев (demo-seed, F5)"
    group = _group(branched[0]["incident_type_code"])
    assert group is not None
    for r in rows:
        if not r.get("branching") and _group(r["incident_type_code"]) == group:
            assert teacher.post(f"/training/scenarios/{r['id']}/archive").status_code == 200
    return group


def _create_session(page: Page, stand: Stand, group: int) -> str:
    page.goto(f"{stand.web}/teacher/sessions")
    page.get_by_role("button", name="новое занятие").click()
    form = page.locator(".cab-card", has_text="Новое занятие")
    assign = form.get_by_label("Назначить группу")
    assign.select_option(assign.locator("option", has_text="Смена 1 (демо)").get_attribute("value"))
    form.get_by_label("Название").fill("e2e: стресс и ветвление")
    form.locator("fieldset.tch-groups label", has_text=re.compile(rf"(^|\s){group}\. ")).locator(
        "input"
    ).check()  # категория событий — группа ветвящегося сценария
    for name in ("Кузнецов Олег Павлович", "Орлова Мария Игоревна", "Лебедев Артём Николаевич"):
        form.get_by_label(f"Роль: {name}").select_option("")  # на звонок выходит один оператор — op2
    form.get_by_label("Сложность вызовов, 1–5").fill("2")
    form.get_by_label("Вес «Развитие ситуации», %").fill("20")
    form.get_by_label(re.compile("Психологический модификатор")).check()
    form.get_by_label("Доля звонков с профилем, %").fill("100")
    form.get_by_label("Вес блока «Работа с заявителем» в итоге, %").fill("20")
    expect(form.get_by_text("участников: 1")).to_be_visible()
    form.get_by_role("button", name="создать занятие").click()
    page.wait_for_url(re.compile(r"/teacher/sessions/[0-9a-f-]{36}$"))
    sid = page.url.rsplit("/", 1)[1]
    page.get_by_role("button", name="начать занятие").click()
    expect(page.get_by_role("button", name="завершить")).to_be_visible()
    return sid


def test_session_psy_branching_report_feedback_readiness(ui: Session) -> None:
    stand = ui.stand
    finish_running_sessions(stand)
    group = _branching_group(stand)
    tpage = ui.new_page("teacher")
    sid = _create_session(tpage, stand, group)
    settings = stand.client("teacher").get(f"/training/sessions/{sid}").json()["settings"]
    assert settings["psy"]["enabled"] and settings["psy"]["share"] == 1 and settings["branch"]["weight"] == 0.2
    try:
        # обучающийся: вызов занятия — заявитель в стрессе и ситуация, которая развивается
        op = ui.new_page("op2")
        call = take_call(op, stand)
        view = stand.client("op2").get(f"/training/calls/{call['call_id']}").json()
        assert view.get("psy") and view.get("branching"), view.keys()
        expect(op.locator(".call-psy")).to_contain_text("ECCS")
        before = party_replies(op).count()
        say(op, "Я на линии, помощь уже едет. Назовите точный адрес.")
        expect(party_replies(op)).to_have_count(before + 1, timeout=30_000)
        op.locator(".call-panel__end").click()
        op.locator(".call-panel").get_by_role("button", name="закрыть").click()
        fill_card(op, reference(stand, call["scenario_id"]))
        save_card(op)
        expect(op.get_by_label("Автооценка")).to_be_visible(timeout=30_000)
        expect(op.get_by_label("Итог ситуации")).to_contain_text("Развитие ситуации")  # F5
        expect(op.get_by_label("Работа с заявителем")).to_be_visible()  # п. 3.7

        # мониторинг → завершить → отчёт → оценка
        tpage.reload()
        expect(tpage.get_by_label("Обучающиеся")).to_contain_text("Волкова")
        tpage.get_by_role("button", name="завершить").click()
        tpage.get_by_role("button", name="отчёт").click()
        tpage.wait_for_url(re.compile(r"/report$"))
        tpage.get_by_role("button", name="оценить все карточки").click()
        row = tpage.locator("tr", has_text="Волкова Ирина Андреевна").first
        row.click()
        sub = tpage.locator("tr.tch-subrow").first
        expect(sub).to_contain_text("ситуация:")  # итог ветвления в отчёте
        sub.get_by_role("button", name="разговор").click()
        expect(sub.get_by_label("Итог ситуации")).to_be_visible()

        # отзыв: черновик модели → правка → сохранение
        feedback = tpage.locator(".tch-feedback").first
        feedback.get_by_role("button", name="предложить отзыв").click()
        expect(feedback.locator(".tch-feedback__meta")).to_contain_text(re.compile("черновик (ИИ|по правилам)"))
        text = feedback.get_by_label("Текст отзыва")
        expect(text).not_to_have_value("")
        text.fill(text.input_value() + "\nСледующее занятие: адрес — в первые 30 секунд.")
        feedback.get_by_role("button", name="сохранить отзыв").click()
        expect(feedback).to_contain_text("виден обучающемуся")
        mine = stand.client("op2").get(f"/assessment/sessions/{sid}/mine").json()
        assert "в первые 30 секунд" in str(mine), mine

        # допуск: обучающийся в списке готовности
        tpage.goto(f"{stand.web}/teacher/readiness")
        expect(tpage.locator("tr", has_text="Волкова Ирина Андреевна").first).to_be_visible()
    finally:
        finish_running_sessions(stand)
