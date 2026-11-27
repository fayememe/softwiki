"""Provision the database behind a knowledge base.

A kb is a directory plus a database. The creation wizard wrote the directory
and registered it, but never created the database, so a freshly created kb was
listed as "unavailable" and could not be selected — which is exactly what
happened with the first user-created kb.

Provisioning is idempotent:

* SQLite: create the directory/file and the schema.
* PostgreSQL: ``CREATE DATABASE`` if it does not exist (connecting through the
  maintenance database), then create the schema in the target database.

Failures are returned, never raised: creating the kb directory itself must not
be rolled back because the database server was unreachable.
"""

import re
from typing import Dict, Optional

#: Database names are identifiers, not parameters, so they are validated rather
#: than escaped.
_SAFE_DB_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


def _create_schema(url: str) -> None:
    from sqlalchemy import create_engine

    # Importing models registers the tables on Base.metadata.
    from softwiki.source_store import models  # noqa: F401
    from softwiki.source_store.db import Base

    engine = create_engine(url)
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()


def ensure_kb_database(kb_path: str) -> Dict[str, Optional[object]]:
    """Create the database for ``kb_path`` if needed.

    Returns ``{"created": bool, "error": str|None, "database": str|None}``.
    """
    from softwiki.config import db_url_for_workspace

    url = db_url_for_workspace(kb_path)

    try:
        if url.startswith("sqlite"):
            _create_schema(url)
            return {"created": True, "error": None, "database": kb_path}

        from sqlalchemy import create_engine, text
        from sqlalchemy.engine import make_url

        parsed = make_url(url)
        name = parsed.database
        if not name or not _SAFE_DB_NAME.match(name):
            return {
                "created": False,
                "error": f"refusing to create database with name {name!r}",
                "database": name,
            }

        admin = parsed.set(database="postgres")
        engine = create_engine(admin, isolation_level="AUTOCOMMIT")
        try:
            with engine.connect() as conn:
                exists = conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :name"),
                    {"name": name},
                ).scalar()
                if not exists:
                    conn.execute(text(f'CREATE DATABASE "{name}"'))
        finally:
            engine.dispose()

        _create_schema(url)
        return {"created": True, "error": None, "database": name}
    except Exception as exc:  # noqa: BLE001 - reported to the caller, not swallowed
        return {"created": False, "error": str(exc)[:300], "database": None}
