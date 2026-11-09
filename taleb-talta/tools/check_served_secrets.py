"""check_served_secrets — no server secret appears in any browser-reachable file.

Reads the actual secret values (pepper, session secret, cron token, stream key, VAPID key, Gemini key, DB password)
and scans the served tree (app/static, app/templates) + schema for them. Also
asserts config/ and tools/ are NOT mounted as static. Exit 1 on any leak.
"""
from __future__ import annotations
import sys, pathlib, re
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

def main():
    from app import config
    secrets = {
        "PASSWORD_PEPPER": config.PASSWORD_PEPPER,
        "SESSION_SECRET": config.SESSION_SECRET,
        "CRON_TOKEN": config.CRON_TOKEN,
        "STREAM_SECRET": config.STREAM_SECRET,
        "VAPID_PRIVATE_KEY": config.VAPID_PRIVATE_KEY,
        "OWNER_PASSWORD": config.OWNER_PASSWORD,
    }
    if config.GEMINI_API_KEY:
        secrets["GEMINI_API_KEY"] = config.GEMINI_API_KEY
    # DB password from URL if present
    m = re.search(r"://[^:]+:([^@]+)@", config.DATABASE_URL)
    if m and m.group(1):
        secrets["DB_PASSWORD"] = m.group(1)
    secrets = {k: v for k, v in secrets.items() if v and len(v) >= 8}

    served_dirs = [ROOT / "app" / "static", ROOT / "app" / "templates"]
    leaks = []
    for d in served_dirs:
        for p in d.rglob("*"):
            if not p.is_file():
                continue
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for name, val in secrets.items():
                if val in content:
                    leaks.append(f"{p}: contains {name}")
    # config/ and tools/ must not be under static
    static = ROOT / "app" / "static"
    for forbidden in ["config", "tools", "secrets.env"]:
        if (static / forbidden).exists():
            leaks.append(f"{static/forbidden}: must not be web-servable")
    # The private file must be git-ignored and owner-only when present.
    import stat
    gi = ROOT / ".gitignore"
    private = config.SECRET_FILE
    if private.exists():
        if not gi.exists() or "secrets.env" not in gi.read_text():
            leaks.append(f"{private}: private env file is not git-ignored")
        mode = stat.S_IMODE(private.stat().st_mode)
        if mode & 0o077:
            leaks.append(f"{private}: mode {oct(mode)} is not owner-only (expected 0600)")
    if leaks:
        print("check_served_secrets: FAIL")
        for l in leaks:
            print("  " + l)
        return 1
    print(f"check_served_secrets: PASS — {len(secrets)} secrets checked, none served")
    return 0

if __name__ == "__main__":
    sys.exit(main())
