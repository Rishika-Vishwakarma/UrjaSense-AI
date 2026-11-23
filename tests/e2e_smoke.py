"""Optional browser end-to-end flow (needs: pip install playwright + a Chrome/Chromium binary).
Run against a running server with a freshly seeded DB:
    python -m database.database_config && python -m backend.app &
    BASE=http://localhost:5000 CHROME=/usr/bin/google-chrome python tests/e2e_smoke.py
"""
import os
from playwright.sync_api import sync_playwright

BASE = os.getenv("BASE", "http://localhost:5000")
CHROME = os.getenv("CHROME", "/usr/bin/google-chrome")


def login(b, email, page_name):
    ctx = b.new_context(viewport={"width": 1280, "height": 900}); pg = ctx.new_page()
    pg.on("dialog", lambda d: d.accept())
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(BASE + "/login.html"); pg.fill("#email", email); pg.fill("#password", "Demo@1234")
    pg.click("button[type=submit]"); pg.wait_for_url(f"**/{page_name}.html"); return ctx, pg, errs


def report(pg, loc, details):
    pg.goto(BASE + "/dashboards/user-dashboard.html#report"); pg.wait_for_selector("#rep")
    pg.select_option("#area_id", "1"); pg.fill("#location_text", loc); pg.fill("#details", details)
    pg.click("#rep button"); pg.wait_for_selector("#result .kv"); return pg.inner_text("#result")


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
    c1, r1, e1 = login(b, "resident1@urjasense.demo", "user-dashboard")
    out1 = report(r1, "Block C, Arera Colony", "transformer sparking, power gone")
    assert "New incident created" in out1, out1
    c2, r2, e2 = login(b, "resident2@urjasense.demo", "user-dashboard")
    out2 = report(r2, "Arera Colony market road", "light gone, transformer noise")
    assert ("Linked to an existing incident" in out2 or "मौजूदा घटना से जोड़ी गई" in out2), out2   # resident2 prefers Hindi
    print("duplicate detection through UI: OK")
    ca, ad, ea = login(b, "admin@urjasense.demo", "admin-dashboard")
    ad.goto(BASE + "/dashboards/admin-dashboard.html#assignments"); ad.wait_for_selector("[data-asg]")
    with ad.expect_response("**/assign"): ad.click("[data-asg]")
    cl, ln, el = login(b, "lineman1@urjasense.demo", "lineman-dashboard")
    for step in ("REPAIR_IN_PROGRESS", "RESOLVED"):
        ln.goto(BASE + "/dashboards/lineman-dashboard.html#status"); ln.wait_for_selector("#st")
        assert step in ln.inner_html("#st"), step
        ln.fill("#rm", "step " + step)
        with ln.expect_response("**/status"): ln.click("#f button")
        ln.goto(BASE + "/dashboards/lineman-dashboard.html#overview"); ln.wait_for_selector(".cards")
    r1.goto(BASE + "/dashboards/user-dashboard.html#feedback"); r1.wait_for_selector("#stars")
    r1.click("#stars button[data-n='5']"); r1.fill("#fb", "Quick restoration")
    with r1.expect_response("**/api/user/ratings"): r1.click("#rate button.btn-primary")
    r1.wait_for_function("document.querySelector('#view').innerText.includes('Quick restoration')")
    print("assign -> repair -> resolve -> rating through UI: OK")
    assert not (e1 + e2 + ea + el), (e1, e2, ea, el)
    b.close()
