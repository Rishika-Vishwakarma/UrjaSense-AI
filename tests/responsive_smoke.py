import sys, json
from playwright.sync_api import sync_playwright
import os
BASE = os.getenv("BASE", "http://localhost:5000")
SHOTS = os.path.join(os.path.dirname(__file__), "..", "reports", "screenshots")
VIEWS = {
 "resident1@urjasense.demo": ("user-dashboard", ["overview","report","map","myreports","notifications","history","feedback","profile"]),
 "lineman1@urjasense.demo": ("lineman-dashboard", ["overview","assigned","details","status","eta","repairs","profile"]),
 "admin@urjasense.demo": ("admin-dashboard", ["overview","users","linemen","incidents","assignments","analytics","areas","feedback","broadcast","logs"]),
}
problems = []
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.getenv("CHROME", "/usr/bin/google-chrome"), args=["--no-sandbox"])
    for email, (page_name, views) in VIEWS.items():
        for label, size in (("desktop", {"width":1366,"height":850}), ("mobile", {"width":390,"height":800})):
            ctx = b.new_context(viewport=size); pg = ctx.new_page()
            pg.on("pageerror", lambda e, em=email: problems.append(f"{em} PAGEERROR {e}"))
            pg.on("console", lambda m, em=email: problems.append(f"{em} CONSOLE {m.text}") if m.type=="error" and "ERR_" not in m.text and "Failed to load resource" not in m.text else None)
            pg.goto(BASE + "/login.html"); pg.fill("#email", email); pg.fill("#password", "Demo@1234")
            pg.click("button[type=submit]"); pg.wait_for_url(f"**/{page_name}.html", timeout=8000)
            for v in views:
                pg.goto(f"{BASE}/dashboards/{page_name}.html#{v}"); pg.wait_for_timeout(700)
                txt = pg.inner_text("#view")
                if "Something went wrong" in txt: problems.append(f"{email}/{v} ERROR VIEW: {txt[:200]}")
                if label == "desktop" or v == "overview":
                    pg.screenshot(path=f"{SHOTS}/{page_name}_{v}_{label}.png")
            # horizontal overflow check on mobile
            if label == "mobile":
                ov = pg.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth + 2")
                if ov: problems.append(f"{email} mobile horizontal overflow")
            ctx.close()
    for pth in ("/", "/login.html", "/register.html"):
        ctx = b.new_context(viewport={"width":390,"height":800}); pg = ctx.new_page(); pg.goto(BASE+pth); pg.wait_for_timeout(400)
        if pg.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth + 2"): problems.append(f"{pth} mobile overflow")
        pg.screenshot(path=f"{SHOTS}/public{pth.replace('/','_') or '_index'}_mobile.png"); ctx.close()
    b.close()
print("PROBLEMS:", json.dumps(problems, indent=1) if problems else "none")
