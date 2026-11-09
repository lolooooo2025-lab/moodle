"""Validate production configuration without printing secret values.

Usage:
  TT_SECRETS_FILE=/etc/taleb-talta/secrets.env python tools/check_production_config.py
  add --require-gemini when the AI provider must be enabled at launch.
"""
from __future__ import annotations
import argparse
import re
import stat
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import config

PLACEHOLDER = re.compile(r"REPLACE_|example\.com|taleb-talta\.local|DB_USER|DB_PASSWORD|DB_HOST|DB_NAME", re.I)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-gemini", action="store_true")
    parser.add_argument("--trial", action="store_true",
                        help="allow a temporary non-production owner password; still reports trial-only status")
    args = parser.parse_args()
    problems: list[str] = []

    def require(name: str, ok: bool):
        if not ok:
            problems.append(name)

    db = urlparse(config.DATABASE_URL)
    require("TT_DATABASE_URL", db.scheme in ("postgresql+asyncpg", "postgresql") and bool(db.hostname)
            and bool(db.path.lstrip("/")) and not PLACEHOLDER.search(config.DATABASE_URL)
            and config.DATABASE_URL != "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/taleb_talta")
    origin = urlparse(config.PUBLIC_ORIGIN)
    require("TT_PUBLIC_ORIGIN", origin.scheme == "https" and bool(origin.netloc)
            and not PLACEHOLDER.search(config.PUBLIC_ORIGIN))
    require("TT_OWNER_PHONE", bool(re.fullmatch(r"01[0125][0-9]{8}", config.OWNER_PHONE)))
    require("TT_OWNER_PASSWORD", bool(config.OWNER_PASSWORD)
            and (args.trial or len(config.OWNER_PASSWORD) >= 12)
            and not PLACEHOLDER.search(config.OWNER_PASSWORD))
    for name in ("TT_PASSWORD_PEPPER", "TT_SESSION_SECRET", "TT_CRON_TOKEN", "TT_STREAM_SECRET", "TT_VAPID_PRIVATE_KEY"):
        value = getattr(config, name.removeprefix("TT_"))
        require(name, bool(re.fullmatch(r"[0-9a-f]{64}", value)) and not PLACEHOLDER.search(value))
    require("TT_VAPID_SUBJECT", config.VAPID_SUBJECT.startswith("mailto:") and "@" in config.VAPID_SUBJECT
            and not PLACEHOLDER.search(config.VAPID_SUBJECT))
    require("TT_COOKIE_SECURE", config.SESSION_COOKIE_SECURE)
    require("TT_DEBUG", not config.DEBUG)
    require("TT_ALLOW_FRAMING", not config.ALLOW_FRAMING)
    if args.require_gemini:
        require("TT_GEMINI_API_KEY", bool(config.GEMINI_API_KEY) and not PLACEHOLDER.search(config.GEMINI_API_KEY))
    if config.SECRET_FILE.exists():
        mode = stat.S_IMODE(config.SECRET_FILE.stat().st_mode)
        require("SECRET_FILE_PERMISSIONS_0600", not (mode & 0o077))
    if problems:
        print("check_production_config: FAIL — missing/invalid names only:")
        for name in problems:
            print("  " + name)
        return 1
    if args.trial:
        print("check_production_config: PASS — TRIAL ONLY; not production-ready (values not printed)")
    else:
        print("check_production_config: PASS — required production values are present (values not printed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
