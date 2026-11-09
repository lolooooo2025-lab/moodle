"""Taleb Talta configuration.

Secrets live ONLY in the process environment or a private local env file
(default: config/secrets.env, overridable with TT_SECRETS_FILE). The file is
git-ignored, never web-servable, and created with mode 0600. Environment values
win over file values. `check_served_secrets` scans served files for these values.
"""
from __future__ import annotations
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent          # taleb-talta/
APP_DIR = BASE_DIR / "app"
STORAGE_DIR = BASE_DIR / "storage"                          # uploads, NOT web-servable
STORAGE_DIR.mkdir(exist_ok=True)

# --- Private local settings ------------------------------------------------
SECRET_FILE = Path(os.environ.get("TT_SECRETS_FILE", str(BASE_DIR / "config" / "secrets.env")))


def _setting(name: str, default: str = "") -> str:
    """Environment first, then the private env file; never a served template."""
    val = os.environ.get(name)
    if val is not None and val != "":
        return val
    if SECRET_FILE.exists():
        for line in SECRET_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, raw = line.split("=", 1)
            if key.strip() == name:
                return raw.strip().strip('"').strip("'")
    return default


def _secret(name: str, default_len: int = 64) -> str:
    """Read a generated secret, or create it once in the private local file."""
    val = _setting(name)
    if val:
        return val
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(SECRET_FILE.parent, 0o700)
    except OSError:
        pass
    val = secrets.token_hex(default_len // 2)
    fd = os.open(SECRET_FILE, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as fh:
        os.fchmod(fh.fileno(), 0o600)
        fh.write(f"{name}={val}\n")
    return val


# --- Database -------------------------------------------------------------
# Production: set TT_DATABASE_URL in the environment/private file. Dev/test:
# tools/devdb.py injects the local pgserver URL into TT_DATABASE_URL.
DATABASE_URL = _setting(
    "TT_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/taleb_talta",
)


def _bounded_int_setting(name: str, default: int, low: int, high: int) -> int:
    """Read a small integer setting without failing startup on a bad value."""
    try:
        value = int(_setting(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


# Pool sizing matters on tiny/free database tiers. Defaults preserve the
# production/VPS behaviour; the free-demo launcher lowers these explicitly.
DB_POOL_SIZE = _bounded_int_setting("TT_DB_POOL_SIZE", 20, 1, 100)
DB_MAX_OVERFLOW = _bounded_int_setting("TT_DB_MAX_OVERFLOW", 40, 0, 200)

# Server-side pepper for password hashing (never in DB, never served).
PASSWORD_PEPPER = _secret("TT_PASSWORD_PEPPER")
# Whether to pepper new hashes. Verification tolerates pepper on/off.
PEPPER_ENABLED = _setting("TT_PEPPER_ENABLED", "1") == "1"
# Secret used to sign session fingerprints / CSRF derivation.
SESSION_SECRET = _secret("TT_SESSION_SECRET")
# Gemini API key — server-side only, used by the AI provider in Wave 6.
GEMINI_API_KEY = _setting("TT_GEMINI_API_KEY")
CRON_TOKEN = _secret("TT_CRON_TOKEN")
# Independent encryption key for owner-only stream credentials. Never served.
STREAM_SECRET = _secret("TT_STREAM_SECRET")
VAPID_PRIVATE_KEY = _secret("TT_VAPID_PRIVATE_KEY", 64)
VAPID_SUBJECT = _setting("TT_VAPID_SUBJECT", "mailto:support@taleb-talta.local")
# First owner bootstrap only. No password fallback is shipped in source code.
OWNER_PHONE = _setting("TT_OWNER_PHONE")
OWNER_PASSWORD = _setting("TT_OWNER_PASSWORD")
BACKUP_DIR = STORAGE_DIR / "backups"

# --- Password policy ------------------------------------------------------
PBKDF2_ITERATIONS = 310_000
PBKDF2_HASH_NAME = "sha256"
PBKDF2_DKLEN = 64                      # 512-bit derived key stored hex
PASSWORD_MIN_LENGTH = 12
PASSWORD_HISTORY = 5                   # disallow last N hashes
PASSWORD_MAX_AGE_DAYS = 180

# --- Sessions -------------------------------------------------------------
SESSION_COOKIE = "tt_session"
SESSION_IDLE_SECONDS = 30 * 60         # 30 min idle
SESSION_ABSOLUTE_SECONDS = 12 * 3600   # 12 h absolute
SESSION_COOKIE_SECURE = _setting("TT_COOKIE_SECURE", "0") == "1"  # set 1 behind HTTPS
# CHIPS partitioned cookie (survives third-party-cookie blocking in iframes).
SESSION_COOKIE_PARTITIONED = _setting("TT_COOKIE_PARTITIONED", "1") == "1"

# --- Lockout / rate limiting ---------------------------------------------
LOGIN_MAX_PER_ACCOUNT = 8              # failures before account lock
LOGIN_MAX_PER_IP = 30                  # failures per IP window
LOCKOUT_SECONDS = 15 * 60
RATE_WINDOW_SECONDS = 60
CHAT_UPLOAD_QUOTA_BYTES = 100 * 1024 * 1024  # uploaded chat files + stickers per user

# --- Brand ----------------------------------------------------------------
SITE_NAME_KEY = "app.name"
# Light-only by product decision (no dark mode). Every theme is a light
# variant built on the measured logo palette (docs/logo-colors.json).
DEFAULT_THEME = "light"
THEMES = ("light", "neutral", "sky")
BRAND_PALETTE = ("#0848A4", "#2FBCF9", "#F8B43C", "#0A1831", "#113B77")
DASHBOARD_BLOCKS = ("courses", "courses_link", "library", "exams", "forum", "chat", "profile", "digest")

# --- App ------------------------------------------------------------------
APP_NAME = "Taleb Talta"
DEBUG = _setting("TT_DEBUG", "0") == "1"
ALLOW_FRAMING = _setting("TT_ALLOW_FRAMING", "0") == "1"
# Temporary free-hosting demo: show a persistence warning and disable local
# backup artifacts. This is NOT a production mode.
DEMO_MODE = _setting("TT_DEMO_MODE", "0") == "1"
# Optional canonical public origin, e.g. https://example.com. When set, browser
# write Origin checks use it instead of trusting arbitrary forwarded hosts.
PUBLIC_ORIGIN = _setting("TT_PUBLIC_ORIGIN")

SITE_TIMEZONE = "Africa/Cairo"
FRIDAY_CAMPAIGN_HOUR = 9
