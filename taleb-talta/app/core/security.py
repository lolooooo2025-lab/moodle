"""Security primitives — Moodle-grade, re-implemented originally.

Passwords: PBKDF2-HMAC-SHA256, 310k iterations, 256-bit random salt per user,
plus a server-side pepper (config.PASSWORD_PEPPER, never in DB / never served).
Stored format:  pbkdf2_sha256$<iterations>$<salt_hex>$<dk_hex>
Verification tolerates a pepper enabled AFTER hashes exist (tries peppered and
unpeppered material), and flags when a re-hash is needed (algorithm/pepper upgrade).
Compare with hmac.compare_digest — never ==.

Inspired by Moodle's swappable password service (lib/moodlelib.php:4245-4261),
but written from the description, not copied.
"""
from __future__ import annotations
import hashlib
import hmac
import secrets
import unicodedata
from app import config

ALGO = "pbkdf2_sha256"

def _material(password: str, use_pepper: bool) -> bytes:
    pw = unicodedata.normalize("NFKC", password).encode("utf-8")
    if use_pepper and config.PEPPER_ENABLED and config.PASSWORD_PEPPER:
        # HMAC the password with the pepper before PBKDF2 (pepper = secret key).
        return hmac.new(config.PASSWORD_PEPPER.encode(), pw, hashlib.sha256).digest()
    return pw

def hash_password(password: str, *, iterations: int | None = None,
                  use_pepper: bool | None = None) -> str:
    iterations = iterations or config.PBKDF2_ITERATIONS
    use_pepper = config.PEPPER_ENABLED if use_pepper is None else use_pepper
    salt = secrets.token_bytes(32)                       # 256-bit salt
    dk = hashlib.pbkdf2_hmac(config.PBKDF2_HASH_NAME,
                             _material(password, use_pepper),
                             salt, iterations, dklen=config.PBKDF2_DKLEN)
    peppered = 1 if (use_pepper and config.PEPPER_ENABLED and config.PASSWORD_PEPPER) else 0
    return f"{ALGO}${iterations}${peppered}${salt.hex()}${dk.hex()}"

def _parse(stored: str):
    parts = stored.split("$")
    if len(parts) == 5 and parts[0] == ALGO:
        return int(parts[1]), int(parts[2]), bytes.fromhex(parts[3]), bytes.fromhex(parts[4])
    # legacy 4-part (no pepper flag)
    if len(parts) == 4 and parts[0] == ALGO:
        return int(parts[1]), 0, bytes.fromhex(parts[2]), bytes.fromhex(parts[3])
    raise ValueError("unrecognised password hash format")

def verify_password(password: str, stored: str) -> tuple[bool, bool]:
    """Return (ok, needs_rehash). Tolerates pepper on/off and flags upgrades."""
    try:
        iterations, peppered, salt, expected = _parse(stored)
    except (ValueError, IndexError):
        return False, False
    # Try the recorded pepper state first, then the opposite (pepper toggled later).
    candidates = [bool(peppered)]
    if config.PASSWORD_PEPPER:
        candidates.append(not bool(peppered))
    for use_pepper in candidates:
        dk = hashlib.pbkdf2_hmac(config.PBKDF2_HASH_NAME,
                                 _material(password, use_pepper),
                                 salt, iterations, dklen=len(expected))
        if hmac.compare_digest(dk, expected):
            needs_rehash = (
                iterations < config.PBKDF2_ITERATIONS
                or (use_pepper != (config.PEPPER_ENABLED and bool(config.PASSWORD_PEPPER)))
            )
            return True, needs_rehash
    return False, False

# --- Password policy ------------------------------------------------------
def password_policy_errors(password: str, phone: str = "", min_length: int | None = None) -> list[str]:
    """Return i18n keys for each violated rule (empty = valid)."""
    errs = []
    if len(password) < (config.PASSWORD_MIN_LENGTH if min_length is None else min_length):
        errs.append("err.password_short")
    classes = sum([
        any(c.islower() for c in password),
        any(c.isupper() for c in password),
        any(c.isdigit() for c in password),
        any(not c.isalnum() for c in password),
    ])
    if classes < 4:
        errs.append("err.password_classes")
    if phone and password == phone:
        errs.append("err.password_equals_phone")
    return errs

# --- CSRF / sesskey -------------------------------------------------------
def new_sesskey() -> str:
    return secrets.token_urlsafe(32)

def check_sesskey(provided: str | None, expected: str | None) -> bool:
    if not provided or not expected:
        return False
    return hmac.compare_digest(provided, expected)

# --- Session fingerprint --------------------------------------------------
def fingerprint(ip: str, user_agent: str) -> str:
    """Hash of IP + User-Agent for hijack detection (prompt §7.2)."""
    raw = f"{ip}|{user_agent}".encode("utf-8", "replace")
    return hmac.new(config.SESSION_SECRET.encode(), raw, hashlib.sha256).hexdigest()

def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)

def hash_token(token: str) -> str:
    """Store only a hash of reset tokens / session ids (never the raw value)."""
    return hashlib.sha256(token.encode()).hexdigest()
