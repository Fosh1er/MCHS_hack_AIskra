"""F6.5 п. 5 и дефект D8 — голосовой полигон с серверными распознаванием и синтезом (через заглушку): страница
открывается из кабинета без ошибок консоли, «Тест голоса» получает WAV, фраза с микрофона распознаётся, ответ
приходит потоком SSE и печатается по мере генерации, затем озвучивается."""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Response, expect

from tests.e2e.conftest import Session
from tests.e2e.mock_llm import REPLY, STT_TEXT

pytestmark = pytest.mark.e2e


def test_voice_lab_tts_stt_stream(ui: Session, browser_name: str) -> None:
    stand, mock = ui.stand, ui.stand.mock
    page = ui.new_page("load001")
    page.goto(f"{stand.web}/student")
    page.get_by_role("link", name="Голосовой полигон").click()
    page.wait_for_url(re.compile(r"/voice-lab/"))
    expect(page.locator("#connection-label")).to_have_text("Не подключён")

    spoken: list[Response] = []
    page.on("response", lambda r: spoken.append(r) if r.url.endswith("/voice-lab/tts") else None)

    # тест голоса: серверный синтез отдаёт WAV
    tts_before = mock.count("/audio/speech")
    with page.expect_response(lambda r: r.url.endswith("/voice-lab/tts")) as tts:
        page.get_by_role("button", name="Тест голоса").click()
    assert tts.value.status == 200, tts.value.text()
    assert tts.value.headers["content-type"].startswith("audio/wav")
    assert int(tts.value.headers.get("content-length") or 0) > 44  # больше заголовка WAV — звук есть
    assert mock.count("/audio/speech") == tts_before + 1
    wav = stand.client("load001").post("/training/voice-lab/tts", json={"input": "(calm) Проверка звука"})
    assert wav.status_code == 200 and wav.content[:4] == b"RIFF", wav.status_code

    if browser_name != "chromium":
        pytest.skip("фраза с микрофона — файл синтетического микрофона есть только у Chromium")

    # разговор: синтетический микрофон → VAD → распознавание → ответ потоком → озвучка
    with page.expect_response(lambda r: r.url.endswith("/voice-lab/chat"), timeout=30_000) as chat:
        page.get_by_role("button", name="Начать разговор").click()
        expect(page.locator(".message.user .message-text").first).to_have_text(STT_TEXT, timeout=20_000)
    assert chat.value.headers["content-type"].startswith("text/event-stream")
    agent = page.locator(".message.agent .message-text").first
    expect(agent).not_to_be_empty(timeout=10_000)
    partial = agent.inner_text()
    expect(agent).to_have_text(REPLY, timeout=20_000)
    assert len(partial) < len(REPLY), "ответ появился целиком — поток не дошёл до страницы"
    expect(page.locator("#tone-notation")).to_contain_text("fear")  # тональность из технической строки модели
    for _ in range(75):  # озвучка ответа: синтез фразы ответа через тот же сервер
        if len(spoken) >= 2:
            break
        page.wait_for_timeout(200)
    assert len(spoken) >= 2 and all(r.ok for r in spoken), [(r.url, r.status) for r in spoken]
    page.get_by_role("button", name="Завершить").click()
    expect(page.locator("#connection-label")).to_have_text("Не подключён")
