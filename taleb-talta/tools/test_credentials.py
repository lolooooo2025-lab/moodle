"""Credentials for local verification only; never hard-code the owner password.

The owner password is read from TT_OWNER_PASSWORD or the private secrets file.
Student passwords below are disposable test-fixture values, not production
accounts. Run verification only against a development/test database.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from app import config

OWNER_PHONE = config.OWNER_PHONE
OWNER_PASSWORD = config.OWNER_PASSWORD
if not OWNER_PHONE:
    raise RuntimeError("Set TT_OWNER_PHONE in the private secrets file before running verification")
if not OWNER_PASSWORD:
    raise RuntimeError("Set TT_OWNER_PASSWORD in the private secrets file before running verification")
STUDENT_PASSWORD = "Student@12345"
