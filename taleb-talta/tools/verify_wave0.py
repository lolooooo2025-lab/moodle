"""Wave-0 end-to-end verification against the REAL PostgreSQL + live server.

Run:  python tools/verify_wave0.py
Exercises: schema import into a fresh DB, register/login/protected access,
session idle-timeout + hijack, wrong/right password + pepper on/off, CSRF,
capability denial, plugin install/uninstall, password reset, lockout, audit.
Prints PASS/FAIL per check and exits non-zero on any failure.
"""
from __future__ import annotations
import os, sys, time, random, subprocess, pathlib
import httpx

BASE = os.environ.get("TT_BASE", "http://127.0.0.1:8000")
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.test_credentials import OWNER_PHONE, OWNER_PASSWORD, STUDENT_PASSWORD
os.environ.setdefault("TT_DATABASE_URL",
    "postgresql+asyncpg://postgres:@/taleb_talta?host=/home/user/tt_pgdata")

RESULTS = []
def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return ok

def rand_phone():
    return "010" + "".join(str(random.randint(0, 9)) for _ in range(8))

UA = {"User-Agent": "tt-verify/1.0"}

def main():
    print("== Taleb Talta Wave-0 verification (real PostgreSQL) ==")
    c = httpx.Client(base_url=BASE, headers=UA, timeout=20, follow_redirects=False)

    # ---- 0. reset rate limits so runs are idempotent ----
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        import devdb, pgserver
        server = devdb.get_server()
        psql_path = pathlib.Path(pgserver.__file__).parent / "pginstall" / "bin" / "psql"
        subprocess.run([str(psql_path), server.get_uri(database="taleb_talta"),
                        "-c", "DELETE FROM rate_limits"], capture_output=True, text=True)
    except Exception:
        pass

    # ---- 1. schema imports cleanly into a FRESH database ----
    print("\n[1] Schema import into a fresh DB")
    try:
        import pgserver
        psql_path = pathlib.Path(pgserver.__file__).parent / "pginstall" / "bin" / "psql"
        dbname = "tt_import_test"
        existing = server.psql("SELECT datname FROM pg_database")
        if dbname in existing:
            server.psql(f"DROP DATABASE {dbname}")
        server.psql(f"CREATE DATABASE {dbname}")
        schema = (ROOT / "database" / "schema.sql").read_text()
        uri = server.get_uri(database=dbname)
        r = subprocess.run([str(psql_path), uri, "-v", "ON_ERROR_STOP=1", "-c", schema],
                           capture_output=True, text=True)
        ok = r.returncode == 0
        n = subprocess.run([str(psql_path), uri, "-tAc",
                            "SELECT count(*) FROM pg_tables WHERE schemaname='public'"],
                           capture_output=True, text=True).stdout.strip()
        check("schema.sql imports with ON_ERROR_STOP", ok,
              (r.stderr.strip()[:200] if not ok else f"{n} tables, no errors"))
        server.psql(f"DROP DATABASE {dbname}")
    except Exception as e:
        check("schema.sql imports with ON_ERROR_STOP", False, f"{type(e).__name__}: {e}")

    # ---- 2. register + login + protected access ----
    print("\n[2] Register / login / protected access")
    phone = rand_phone()
    pw = STUDENT_PASSWORD
    r = c.post("/api/auth/register", json={"phone": phone, "password": pw,
               "name": "طالب تجريبي", "guardian_phone": rand_phone(),
               "division_id": 1, "website": "", "elapsed_ms": 5000})
    j = r.json()
    check("register succeeds", j["success"], j["message"])
    # weak password rejected
    r = c.post("/api/auth/register", json={"phone": rand_phone(), "password": "short",
               "name": "x", "guardian_phone": rand_phone(), "division_id": 1,
               "website": "", "elapsed_ms": 5000})
    check("weak password rejected (Egyptian msg)", not r.json()["success"], r.json()["message"])
    # honeypot rejected
    r = c.post("/api/auth/register", json={"phone": rand_phone(), "password": pw,
               "name": "x", "guardian_phone": rand_phone(), "division_id": 1,
               "website": "spam", "elapsed_ms": 5000})
    check("honeypot rejected", not r.json()["success"])
    # wrong password
    r = c.post("/api/auth/login", json={"phone": phone, "password": "Wrong@12345678"})
    check("wrong password rejected", not r.json()["success"], r.json()["message"])
    # correct login
    r = c.post("/api/auth/login", json={"phone": phone, "password": pw})
    j = r.json()
    check("correct login accepted", j["success"], j["message"])
    student_sesskey = j["data"]["sesskey"]
    # protected page with cookie
    r = c.get("/")
    check("protected dashboard returns 200 when logged in", r.status_code == 200)
    check("dashboard is RTL", 'dir="rtl"' in r.text)
    # protected API
    r = c.get("/api/auth/me")
    check("me API returns the student", r.json()["success"] and r.json()["data"]["phone"] == phone)
    # anonymous protected access
    anon = httpx.Client(base_url=BASE, headers=UA, timeout=20)
    r = anon.get("/api/auth/me")
    check("anonymous me API rejected", not r.json()["success"])
    r = anon.get("/")
    check("anonymous dashboard redirects to login", r.status_code in (303, 307))

    # ---- 3. CSRF (sesskey) ----
    print("\n[3] CSRF / sesskey")
    r = c.post("/api/users/profile", json={"name": "بدون مفتاح"})  # no X-Sesskey
    check("write without sesskey rejected (403)", r.status_code == 403)
    r = c.post("/api/users/profile", json={"name": "اسم جديد"},
               headers={"X-Sesskey": student_sesskey})
    check("write with valid sesskey accepted", r.json()["success"], r.json()["message"])

    # ---- 4. capability denial ----
    print("\n[4] Capability-based authorization")
    r = c.get("/api/plugins")
    check("student denied plugin/manage (403)", r.status_code == 403)
    # owner login
    oc = httpx.Client(base_url=BASE, headers=UA, timeout=20)
    r = oc.post("/api/auth/login", json={"phone": OWNER_PHONE, "password": OWNER_PASSWORD})
    j = r.json()
    check("owner login", j["success"], j["message"])
    owner_sesskey = j["data"]["sesskey"]
    r = oc.get("/api/plugins")
    check("owner allowed plugin/manage", r.status_code == 200 and r.json()["success"])

    # ---- 5. plugin install / uninstall ----
    print("\n[5] Plugin lifecycle")
    # Make the lifecycle deterministic even when a previous wave left the demo
    # plugin enabled: uninstall (keep data) returns it to the present state.
    current = {p["component"]: p for p in oc.get("/api/plugins").json()["data"]}
    if current.get("tool_backup", {}).get("status") in ("installed", "enabled", "disabled"):
        oc.post("/api/plugins/uninstall", json={"component": "tool_backup", "purge": False},
                headers={"X-Sesskey": owner_sesskey})
    r = oc.post("/api/plugins/install", json={"component": "tool_backup"},
                headers={"X-Sesskey": owner_sesskey})
    j = r.json()
    check("plugin install succeeds", j["success"], str(j.get("data")))
    r = oc.get("/api/plugins")
    plugins = {p["component"]: p for p in r.json()["data"]}
    check("plugin shows installed", plugins.get("tool_backup", {}).get("status") == "installed")
    # menu item added
    r = oc.post("/api/plugins/enable", json={"component": "tool_backup"},
                headers={"X-Sesskey": owner_sesskey})
    check("plugin enable succeeds", r.json()["success"])
    # uninstall keeps data
    r = oc.post("/api/plugins/uninstall", json={"component": "tool_backup", "purge": False},
                headers={"X-Sesskey": owner_sesskey})
    check("plugin uninstall (keep data) succeeds", r.json()["success"])
    r = oc.get("/api/plugins")
    plugins = {p["component"]: p for p in r.json()["data"]}
    check("plugin back to present after uninstall",
          plugins.get("tool_backup", {}).get("status") == "present")
    # student cannot install
    r = c.post("/api/plugins/install", json={"component": "tool_backup"},
               headers={"X-Sesskey": student_sesskey})
    check("student cannot install plugin (403)", r.status_code == 403)

    # ---- 6. password reset ----
    print("\n[6] Password reset flow")
    r = c.post("/api/auth/forgot", json={"phone": phone})
    j = r.json()
    token = (j.get("data") or {}).get("token")
    check("forgot returns token in debug", j["success"] and bool(token))
    if token:
        newpw = "NewPass@98765"
        r = c.post("/api/auth/reset", json={"token": token, "new_password": newpw})
        check("reset with valid token succeeds", r.json()["success"], r.json()["message"])
        r = c.post("/api/auth/login", json={"phone": phone, "password": newpw})
        check("login with new password works", r.json()["success"])
        student_sesskey = r.json()["data"]["sesskey"]

    # ---- 7. session idle timeout + hijack (direct DB manipulation) ----
    print("\n[7] Session timeout + hijack detection")
    import asyncio
    from sqlalchemy import text
    from app.core.db import get_engine, dispose_db
    async def session_tests():
        eng = get_engine()
        # idle timeout: age the student's session last_seen beyond 30 min
        async with eng.begin() as conn:
            await conn.execute(text(
                "UPDATE sessions SET last_seen = now() - interval '31 minutes' "
                "WHERE revoked = false AND user_id = (SELECT id FROM users WHERE phone=:p)"),
                {"p": phone})
        r = c.get("/api/auth/me")
        check("idle-timeout session rejected", not r.json()["success"], r.json()["message"])
        # re-login, then hijack: change User-Agent
        r = c.post("/api/auth/login", json={"phone": phone, "password": newpw})
        check("re-login after idle timeout", r.json()["success"])
        hijack = httpx.Client(base_url=BASE, headers={"User-Agent": "attacker/9.9"}, timeout=20)
        hijack.cookies.update(c.cookies)
        r = hijack.get("/api/auth/me")
        check("hijacked session (UA mismatch) rejected", not r.json()["success"])
        await dispose_db()
    asyncio.run(session_tests())

    # ---- 8. account lockout ----
    print("\n[8] Account lockout")
    lock_phone = rand_phone()
    c.post("/api/auth/register", json={"phone": lock_phone, "password": pw,
           "name": "قفل", "guardian_phone": rand_phone(), "division_id": 1,
           "website": "", "elapsed_ms": 5000})
    lc = httpx.Client(base_url=BASE, headers=UA, timeout=20)
    last = None
    for i in range(9):
        last = lc.post("/api/auth/login", json={"phone": lock_phone, "password": "Wrong@00000000"}).json()
    check("account locked after repeated failures",
          last and not last["success"] and "مقفول" in last["message"], last["message"] if last else "")

    # ---- 9. pepper on/off + hashing ----
    print("\n[9] Password hashing / pepper")
    from app.core import security
    h_peppered = security.hash_password("Test@12345678", use_pepper=True)
    ok, _ = security.verify_password("Test@12345678", h_peppered)
    check("peppered hash verifies", ok)
    h_unpeppered = security.hash_password("Test@12345678", use_pepper=False)
    ok, _ = security.verify_password("Test@12345678", h_unpeppered)
    check("unpeppered hash verifies with pepper enabled (tolerant)", ok)
    ok, _ = security.verify_password("Wrong@12345678", h_peppered)
    check("wrong password fails constant-time compare", not ok)
    check("hash format is pbkdf2_sha256", h_peppered.startswith("pbkdf2_sha256$310000$"))

    # ---- 10. audit log recorded ----
    print("\n[10] Audit log")
    async def audit_test():
        from sqlalchemy import text
        from app.core.db import get_engine, dispose_db
        eng = get_engine()
        async with eng.connect() as conn:
            rows = (await conn.execute(text(
                "SELECT action, severity FROM audit_log ORDER BY id"))).all()
        actions = {r[0] for r in rows}
        need = ["user.registered", "user.logged_in", "user.login_failed",
                "plugin.installed", "plugin.uninstalled", "capability.denied",
                "session.hijack_detected", "user.locked_out", "user.password_changed"]
        for a in need:
            check(f"audit recorded {a}", a in actions)
        sevs = {r[1] for r in rows}
        check("audit severities are valid ENUM", sevs <= {"info", "notice", "warning", "critical"},
              str(sevs))
        await dispose_db()
    asyncio.run(audit_test())

    # ---- summary ----
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print(f"\n== RESULT: {passed}/{total} checks passed ==")
    failed = [n for n, ok, _ in RESULTS if not ok]
    if failed:
        print("FAILED:", failed)
        sys.exit(1)
    print("ALL WAVE-0 CHECKS PASSED")

if __name__ == "__main__":
    main()
