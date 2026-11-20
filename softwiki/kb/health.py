"""Cheap availability probe for a knowledge base's database.

`/api/kb` deliberately reads only the filesystem (design D1: listing must not
open a database, or `kb_list` would warm every kb's cache). That is right for
agents but wrong for the UI: a kb directory can exist while its database was
never created in *this* instance's PostgreSQL, and switching to it then fails
with a 500.

This module answers "can this instance actually serve this kb?" with a single
`SELECT 1`, bounded by a timeout and cached for a few seconds.
"""

from __future__ import annotations

import os
import time
from typing import Optional, Tuple

from sqlalchemy import create_engine, text

from softwiki.config import db_url_for_workspace

# (available, reason) per kb path, with the monotonic timestamp of the probe.
_cache: dict[str, Tuple[float, bool, Optional[str]]] = {}

_TTL = float(os.getenv("SOFTWIKI_KB_PROBE_TTL", "15"))
_TIMEOUT = int(os.getenv("SOFTWIKI_KB_PROBE_TIMEOUT", "3"))


def _probe(url: str) -> Tuple[bool, Optional[str]]:
    # SQLite silently creates a missing file, so a passing SELECT 1 would hide
    # exactly the problem this probe exists to detect.
    if url.startswith("sqlite"):
        from sqlalchemy.engine import make_url

        try:
            path = make_url(url).database
        except Exception as exc:  # noqa: BLE001 - malformed url is the answer
            return False, f"cannot parse database url: {exc}"
        if path and not os.path.isfile(path):
            return False, f"database file not found: {path}"

    connect_args = {}
    if url.startswith("postgresql"):
        # psycopg2 honours connect_timeout (seconds).
        connect_args = {"connect_timeout": max(1, _TIMEOUT)}
    engine = None
    try:
        engine = create_engine(url, connect_args=connect_args)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, None
    except Exception as exc:  # noqa: BLE001 - a failed probe must not 500 the listing
        message = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
        return False, message[:200]
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception:  # noqa: BLE001 - disposal failure is not actionable
                pass


def probe_kb(workspace_path: str, use_cache: bool = True) -> Tuple[bool, Optional[str]]:
    """Return (available, reason) for one kb. Never raises."""
    key = os.path.abspath(workspace_path)
    now = time.monotonic()
    if use_cache:
        cached = _cache.get(key)
        if cached and now - cached[0] < _TTL:
            return cached[1], cached[2]

    try:
        url = db_url_for_workspace(key)
    except Exception as exc:  # noqa: BLE001 - misconfiguration must be reported, not raised
        result: Tuple[bool, Optional[str]] = (False, f"cannot derive database url: {exc}")
    else:
        result = _probe(url)

    _cache[key] = (now, result[0], result[1])
    return result


def invalidate(workspace_path: Optional[str] = None) -> None:
    """Drop cached probe results (call after creating a kb or its database)."""
    if workspace_path is None:
        _cache.clear()
    else:
        _cache.pop(os.path.abspath(workspace_path), None)
