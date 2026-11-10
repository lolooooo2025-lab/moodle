"""Verify Neon `.env.local` loading and Postgres URL mapping.

Uses synthetic values only. Prints key names and PASS/FAIL — never values.

    python tools/check_neon_env.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.neon_env import load_neon_env, normalize_database_url, parse_env_file  # noqa: E402

FAKE_DIRECT = "postgresql://u:p@ep-cool-dark-123456.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
FAKE_POOLED = "postgresql://u:p@ep-cool-dark-123456-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require&options=endpoint%3Dep-cool-dark-123456"

results: list[tuple[bool, str]] = []


def check(ok: bool, label: str) -> None:
    results.append((bool(ok), label))


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)

        # --- parsing -------------------------------------------------------
        f = base / ".env"
        write(f, "# comment\n\nexport DATABASE_URL=\"" + FAKE_POOLED + "\"\nPLAIN='abc=def'\nBAD LINE\n")
        parsed = parse_env_file(f)
        check(parsed.get("DATABASE_URL") == FAKE_POOLED, "parse: export prefix + double quotes")
        check(parsed.get("PLAIN") == "abc=def", "parse: single quotes + '=' inside value")
        check("BAD LINE" not in parsed and len(parsed) == 2, "parse: comments/blank/invalid skipped")
        check(parse_env_file(base / "missing.env") == {}, "parse: missing file is tolerated")

        # --- precedence: .env.local beats .env ------------------------------
        write(base / ".env.local", f"DATABASE_URL_UNPOOLED={FAKE_DIRECT}\nNEON_BRANCH=production\n")
        env: dict[str, str] = {}
        added = load_neon_env(base, env)
        check(env.get("NEON_BRANCH") == "production", "load: .env.local key present")
        check("DATABASE_URL_UNPOOLED" in added and "TT_DATABASE_URL" in added, "load: returns key names")
        check(all(v not in added for v in (FAKE_DIRECT, FAKE_POOLED)), "load: never returns values")

        # --- direct endpoint preferred over pooled --------------------------
        check(env.get("TT_DATABASE_URL", "").startswith("postgresql+asyncpg://"), "map: asyncpg scheme")
        check("-pooler" not in env.get("TT_DATABASE_URL", ""), "map: unpooled endpoint preferred")
        check("ssl=require" in env.get("TT_DATABASE_URL", ""), "map: sslmode -> ssl")
        check("channel_binding" not in env.get("TT_DATABASE_URL", ""), "map: channel_binding dropped")

        # --- real environment wins ------------------------------------------
        env2 = {"NEON_BRANCH": "from-environ", "TT_DATABASE_URL": "postgresql+asyncpg://kept/db"}
        load_neon_env(base, env2)
        check(env2["NEON_BRANCH"] == "from-environ", "precedence: real env beats .env.local")
        check(env2["TT_DATABASE_URL"] == "postgresql+asyncpg://kept/db", "precedence: TT_DATABASE_URL untouched")

        # --- pooled-only falls back and fails closed ------------------------
        base2 = base / "pooled-only"
        base2.mkdir()
        write(base2 / ".env.local", f"DATABASE_URL={FAKE_POOLED}\n")
        try:
            load_neon_env(base2, {})
            check(False, "pooled-only: should fail closed")
        except ValueError as exc:
            check("DATABASE_URL_UNPOOLED" in str(exc), "pooled-only: helpful error mentions unpooled key")

        # --- .env.local overrides a value from .env -------------------------
        base3 = base / "override"
        base3.mkdir()
        write(base3 / ".env", "NEON_BRANCH=stale\nONLY_IN_ENV=yes\n")
        write(base3 / ".env.local", "NEON_BRANCH=production\n")
        env3: dict[str, str] = {}
        load_neon_env(base3, env3)
        check(env3.get("NEON_BRANCH") == "production", "precedence: .env.local beats .env")
        check(env3.get("ONLY_IN_ENV") == "yes", "load: .env-only keys still loaded")

        # --- TT_NEON_ENV_FILE override ---------------------------------------
        extra = base / "extra.env"
        write(extra, "NEON_BRANCH=extra-wins\n")
        env4 = {"TT_NEON_ENV_FILE": str(extra)}
        load_neon_env(base, env4)
        check(env4.get("NEON_BRANCH") == "extra-wins", "override: TT_NEON_ENV_FILE has top file precedence")

    # --- normalizer edge cases ---------------------------------------------
    check(normalize_database_url("postgres://u:p@h/db") == "postgresql+asyncpg://u:p@h/db",
          "normalize: postgres:// alias")
    for bad, label in (("mysql://u:p@h/db", "non-postgres scheme"),
                       ("postgresql://u:p@h/", "missing database name")):
        try:
            normalize_database_url(bad)
            check(False, f"normalize: rejects {label}")
        except ValueError:
            check(True, f"normalize: rejects {label}")

    # --- launcher still exposes the normalizer ------------------------------
    sys.path.insert(0, str(ROOT / "deploy" / "free-demo"))
    import importlib
    start = importlib.import_module("start")
    check(callable(getattr(start, "normalize_database_url", None)), "launcher: normalize_database_url re-exported")
    check(callable(getattr(start, "load_neon_env", None)), "launcher: load_neon_env wired")

    # --- the env files must stay out of git ---------------------------------
    for name in (".env", ".env.local"):
        proc = subprocess.run(["git", "check-ignore", "-q", name], cwd=ROOT)
        check(proc.returncode == 0, f"gitignore: {name} is ignored")

    failed = [label for ok, label in results if not ok]
    for ok, label in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    print(f"\ncheck_neon_env: {len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
