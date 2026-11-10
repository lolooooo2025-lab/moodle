"""Preview login regression: CHIPS succeeds; total cookie rejection is honest.

Top-level shell: https://shell.test:9443; embedded app: https://app.test:8443.
The hosts are different registrable domains. Mode 1 uses Chromium's real
third-party-cookie phase-out (partitioned cookies should work). Mode 2 strips
cookies only from iframe requests, emulating an embedder/browser that rejects
even CHIPS. In that mode the UI must not claim success, and its explicit
standalone-window action must produce a working first-party dashboard.

Requires the HTTPS app (:8443) and tools/iframe_embedder.py (:9443).
"""
import os
import pathlib
import sys

os.environ["LD_LIBRARY_PATH"] = "/tmp/chromium-libs/lib"
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.test_credentials import OWNER_PHONE, OWNER_PASSWORD, STUDENT_PASSWORD

EMBEDDER = "https://shell.test:9443"
APP = "https://app.test:8443"
PHONE = OWNER_PHONE
PASSWORD = OWNER_PASSWORD
RESOLVER = "MAP shell.test 127.0.0.1, MAP app.test 127.0.0.1"
SHOTS = pathlib.Path(__file__).resolve().parents[1] / "docs/screenshots"
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""), flush=True)


def login(page_or_frame):
    page_or_frame.locator("#phone").fill(PHONE)
    page_or_frame.locator("#password").fill(PASSWORD)
    page_or_frame.locator("#login-form button[type=submit]").click()


def run(reject_all=False):
    with sync_playwright() as p:
        args = ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
                f"--host-resolver-rules={RESOLVER}", "--test-third-party-cookie-phaseout"]
        browser = p.chromium.launch(executable_path="/tmp/chromium-bin", headless=True, args=args)
        ctx = browser.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 900},
                                  service_workers="block")
        if reject_all:
            def reject_frame_cookies(route):
                request = route.request
                try:
                    frame = request.frame
                except Exception:
                    frame = None
                if frame is None or frame.parent_frame is None:
                    route.continue_()
                    return
                headers = dict(request.headers)
                headers.pop("cookie", None)
                # route.fetch uses Node's DNS, not Chromium's host-resolver
                # rules. Send to loopback while preserving the public Host.
                import httpx
                url = request.url.replace("https://app.test:8443", "https://127.0.0.1:8443")
                response = httpx.request(request.method, url, headers=headers,
                                         content=request.post_data_buffer, verify=False,
                                         follow_redirects=False, timeout=15, trust_env=False)
                response_headers = dict(response.headers)
                for key in ("set-cookie", "content-encoding", "content-length", "transfer-encoding"):
                    response_headers.pop(key, None)
                route.fulfill(status=response.status_code, headers=response_headers, body=response.content)
            ctx.route("**/*", reject_frame_cookies)
        page = ctx.new_page()
        page.goto(EMBEDDER, wait_until="networkidle")
        frame = page.frame_locator("#f")
        frame.locator("#phone").wait_for(timeout=15000)
        check("standalone escape is available before login", frame.locator("#preview-login-help").is_visible())
        login(frame)
        page.wait_for_timeout(1800)
        appframe = next((f for f in page.frames if f.url.startswith(APP)), None)
        if not reject_all:
            body = appframe.content() if appframe else ""
            check("CHIPS login reaches dashboard", appframe and "/login" not in appframe.url and "logout-btn" in body,
                  appframe.url if appframe else "no frame")
            cookies = [c for c in ctx.cookies(APP) if c["name"] == "tt_session"]
            check("session cookie is secure and partitioned", bool(cookies) and cookies[0]["secure"]
                  and cookies[0]["sameSite"] == "None" and bool(cookies[0].get("partitionKey")))
            if appframe:
                appframe.evaluate("window.scrollTo(0,0)")
                page.screenshot(path=str(SHOTS / "45-preview-chips-dashboard.png"), full_page=True)
        else:
            check("rejected cookie does not redirect into a false success", appframe and appframe.url.endswith("/login"))
            check("cookie rejection shows an actionable error", frame.locator("#login-form .form-error").is_visible())
            check("no success toast after rejected cookie", "تمام" not in frame.locator("#toast-region").inner_text())
            check("standalone action remains visible", frame.locator("#preview-login-help a").is_visible())
            appframe.evaluate("window.scrollTo(0,0)")
            page.screenshot(path=str(SHOTS / "46-preview-cookie-help.png"), full_page=True)
            with page.expect_popup() as popup_info:
                frame.locator("#preview-login-help a").click()
            standalone = popup_info.value
            standalone.wait_for_load_state("networkidle")
            check("escape opens the app first-party", standalone.url.startswith(APP + "/login"))
            login(standalone)
            standalone.wait_for_url(APP + "/", timeout=10000)
            standalone.wait_for_load_state("networkidle")
            check("standalone login renders the real dashboard", standalone.locator("#logout-btn").count() == 1
                  and standalone.locator("#login-form").count() == 0)
            standalone.evaluate("window.scrollTo(0,0)")
            standalone.screenshot(path=str(SHOTS / "47-preview-standalone-dashboard.png"), full_page=True)
        browser.close()


def main():
    SHOTS.mkdir(parents=True, exist_ok=True)
    print("== Cross-site iframe: partitioned cookies enabled ==")
    run(reject_all=False)
    print("== Cross-site iframe: all cookie storage rejected ==")
    run(reject_all=True)
    passed = sum(ok for _, ok in RESULTS)
    print(f"\n== PREVIEW LOGIN: {passed}/{len(RESULTS)} passed ==")
    if passed != len(RESULTS):
        print("FAILED:", [name for name, ok in RESULTS if not ok])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
