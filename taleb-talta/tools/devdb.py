"""Dev/test database: a REAL PostgreSQL via pgserver (no mocks).

Usage:
  python tools/devdb.py url      # print the asyncpg URL (starts server if needed)
  python tools/devdb.py create   # create the taleb_talta database
The server keeps running as a daemon; tests and the dev server connect to it.
"""
from __future__ import annotations
import sys
import os
from pathlib import Path

PGDATA = Path(os.environ.get("TT_PGDATA", "/home/user/tt_pgdata"))

def get_server():
    import pgserver
    PGDATA.mkdir(parents=True, exist_ok=True)
    # cleanup_mode=None leaves postgres running after this process exits.
    return pgserver.get_server(str(PGDATA), cleanup_mode=None)

def get_url(database: str = "taleb_talta") -> str:
    server = get_server()
    uri = server.get_uri(database=database)          # postgresql://...
    # SQLAlchemy async driver
    return uri.replace("postgresql://", "postgresql+asyncpg://", 1)

def ensure_database(database: str = "taleb_talta"):
    server = get_server()
    # psql() connects to the default 'postgres' database; CREATE DATABASE is
    # idempotent-guarded here (it errors if the DB already exists).
    existing = server.psql("SELECT datname FROM pg_database")
    if database not in existing:
        server.psql(f"CREATE DATABASE {database}")
    return get_url(database)

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "url"
    if cmd == "create":
        print(ensure_database())
    else:
        ensure_database()
        print(get_url())
