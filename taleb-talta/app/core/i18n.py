"""i18n — the t() helper. All user-visible strings come from app/lang/<lang>.py.

Moodle pattern: a string manager + per-component lang files (string_manager_standard.php).
Here: a dict per language, t(key) falls back to the key if missing. A second language
is added by dropping app/lang/en.py — no code change.
"""
from __future__ import annotations
import importlib
from functools import lru_cache

DEFAULT_LANG = "ar"

@lru_cache(maxsize=8)
def _load(lang: str) -> dict:
    strings: dict = {}
    try:
        mod = importlib.import_module(f"app.lang.{lang}")
        strings.update(getattr(mod, "STRINGS", {}))
    except ModuleNotFoundError:
        pass
    # Merge plugin language files (Moodle: per-component lang packs).
    from app import config
    pdir = config.APP_DIR / "plugins"
    if pdir.exists():
        for langfile in sorted(pdir.glob(f"*/*/lang/{lang}.py")):
            parts = langfile.relative_to(pdir).parts
            ptype, pname = parts[0], parts[1]
            try:
                pmod = importlib.import_module(f"app.plugins.{ptype}.{pname}.lang.{lang}")
                strings.update(getattr(pmod, "STRINGS", {}))
            except ModuleNotFoundError:
                continue
    return strings

def reload_strings():
    """Purge the string cache (after a plugin install/uninstall)."""
    _load.cache_clear()

def t(key: str, lang: str = DEFAULT_LANG, **params) -> str:
    """Translate a key. Falls back to default lang, then to the key itself."""
    s = _load(lang).get(key)
    if s is None and lang != DEFAULT_LANG:
        s = _load(DEFAULT_LANG).get(key)
    if s is None:
        return key
    if params:
        try:
            return s.format(**params)
        except (KeyError, IndexError):
            return s
    return s

def available_languages() -> list[str]:
    return ["ar"]
