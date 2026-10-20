"""Скриншоты новых функций для финальной презентации (F1, F2, F4, F5). Стенд — localhost:5173 в режиме demo."""
import sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
WEB = "http://localhost:5173"

def ctx_for(browser, login=None, vw=1600, vh=900):
    ctx = browser.new_context(viewport={"width": vw, "height": vh}, device_scale_factor=2, locale="ru-RU", timezone_id="Europe/Moscow")
    page = ctx.new_page(); page.set_default_timeout(20000)
    if login:
        page.goto(f"{WEB}/")
        r = page.request.post(f"{WEB}/api/v1/auth/demo-login", data={"login": login}); assert r.ok, r.text()
        page.request.post(f"{WEB}/api/v1/auth/onboarding", data={"action": "dismiss"})
    return ctx, page

with sync_playwright() as pw:
    b = pw.chromium.launch()
    # F2 — вход одной кнопкой
    ctx, p = ctx_for(b, vw=1440, vh=1000)
    p.goto(f"{WEB}/"); p.wait_for_load_state("networkidle"); time.sleep(0.5)
    p.screenshot(path=str(OUT / "f2_login.png"), full_page=True); ctx.close()
    # F4 — методика
    ctx, p = ctx_for(b, "teacher")
    p.goto(f"{WEB}/teacher/methodology"); p.wait_for_load_state("networkidle"); time.sleep(0.8)
    p.screenshot(path=str(OUT / "f4_methodology.png")); 
    # F5 — граф ветвящегося сценария
    tpls = p.request.get(f"{WEB}/api/v1/training/branch-templates").json()
    tpl = next(t for t in tpls if "ожар" in t["title"]) if any("ожар" in t["title"] for t in tpls) else tpls[0]
    r = p.request.post(f"{WEB}/api/v1/training/scenarios/generate", data={"count": 1, "groups": [int(tpl["incident_codes"][0][:1] or 1)] if tpl["incident_codes"] else [], "difficulty": 3, "branching": tpl["id"]})
    print("generate", r.status, r.text()[:200])
    p.goto(f"{WEB}/teacher/scenarios"); p.wait_for_load_state("networkidle"); time.sleep(0.8)
    p.locator("tr", has_text="ветвление").first.click(); time.sleep(0.8)
    p.get_by_role("radio", name="ветвление").or_(p.get_by_role("button", name="ветвление")).first.click(); time.sleep(0.8)
    g = p.locator(".branch-graph").first
    g.screenshot(path=str(OUT / "f5_graph.png"))
    p.screenshot(path=str(OUT / "f5_bank.png")); ctx.close()
    # F1 + F4 — звонок: поток ответа и шкала ECCS
    ctx, p = ctx_for(b, "op1", vw=1600, vh=900)
    p.goto(f"{WEB}/arm/112/journal"); p.wait_for_load_state("networkidle")
    p.get_by_role("button", name="учебный вызов").click()
    p.get_by_role("button", name="Ответить").click()
    p.wait_for_url("**/arm/112/*?call=*"); time.sleep(1.5)
    box = p.get_by_label("Реплика")
    box.fill("Служба 112. Что у вас случилось?"); box.press("Enter")
    p.locator(".arm-msg--streaming").wait_for(timeout=15000)
    p.locator(".arm-msg--streaming .arm-msg__fresh").first.wait_for(timeout=15000); time.sleep(0.9)
    p.locator(".call-panel").screenshot(path=str(OUT / "f1_streaming.png"))
    p.locator(".arm-msg--streaming").wait_for(state="detached", timeout=30000); time.sleep(0.5)
    box.fill("Успокойтесь! Назовите адрес."); box.press("Enter")
    p.locator(".arm-msg--streaming").wait_for(timeout=15000); time.sleep(0.6)
    p.locator(".call-panel").screenshot(path=str(OUT / "f1_state.png"))
    p.locator(".arm-msg--streaming").wait_for(state="detached", timeout=30000); time.sleep(0.5)
    p.locator(".call-panel").screenshot(path=str(OUT / "f1_final.png"))
    p.screenshot(path=str(OUT / "f1_screen.png"))
    ctx.close(); b.close()
print("ok", sorted(x.name for x in OUT.iterdir()))
