"""Audit log for write and sensitive operations.

Design (docs/02-design/auth-oidc.md §7):

* **Write and sensitive operations are recorded. Read-only queries are not** —
  they are high volume and low value. Aggregates can be derived elsewhere.
* The log is a *system* log: it lives **outside** the knowledge base database
  so deleting documents or dropping a kb never erases the history of it.
* Recording never breaks the operation it describes. A failure to write the
  audit row is logged loudly and swallowed.

Storage is append-only JSON Lines at ``<workspaces root>/.softwiki-audit/audit.log``
(or ``SOFTWIKI_AUDIT_LOG``). Rotate by moving the file aside; nothing reads it
back for correctness.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Optional

from softwiki.config import get_workspaces_root

logger = logging.getLogger(__name__)

#: Identity of the caller for the current request, set by the auth layer.
_ACTOR_CTX: ContextVar[dict | None] = ContextVar("softwiki_actor", default=None)

_WRITE_LOCK = threading.Lock()


def set_actor(actor: Optional[dict]):
    """Attach the current caller to subsequent audit records."""
    return _ACTOR_CTX.set(actor)


def reset_actor(token) -> None:
    _ACTOR_CTX.reset(token)


def current_actor() -> dict:
    """Return the caller description, defaulting to the single-machine superuser.

    No identity layer means no accounts: every call is the machine's own
    superuser. That is exactly what the audit trail should say.
    """
    actor = _ACTOR_CTX.get()
    if actor:
        return dict(actor)
    return {"mode": "off", "identity": "superuser"}


def audit_log_path() -> str:
    explicit = os.getenv("SOFTWIKI_AUDIT_LOG")
    if explicit:
        os.makedirs(os.path.dirname(os.path.abspath(explicit)), exist_ok=True)
        return os.path.abspath(explicit)
    root = os.path.join(get_workspaces_root(), ".softwiki-audit")
    os.makedirs(root, exist_ok=True)
    return os.path.join(root, "audit.log")


def record(
    action: str,
    *,
    target: Any = None,
    result: str = "ok",
    detail: Optional[str] = None,
    capability: Optional[str] = None,
    actor: Optional[dict] = None,
    source_ip: Optional[str] = None,
    **extra: Any,
) -> dict:
    """Append one audit record and return it.

    ``result`` is deliberately free-form: ``ok``, ``denied``, ``error`` and
    ``cancelled`` are the ones the built-in call sites use.
    """
    who = dict(actor) if actor else current_actor()
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "action": action,
        "mode": who.get("mode"),
        "identity": who.get("identity"),
        "role": who.get("role"),
        "source_ip": source_ip or who.get("source_ip"),
        "kb": who.get("kb"),
        "target": _plain(target),
        "capability": capability,
        "result": result,
        "detail": detail,
    }
    if extra:
        entry["extra"] = _plain(extra)

    try:
        line = json.dumps(entry, ensure_ascii=False, default=str)
        path = audit_log_path()
        with _WRITE_LOCK:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception as exc:  # noqa: BLE001 - auditing must not break the action
        logger.error("failed to write audit record %r: %s", action, exc, exc_info=True)
    return entry


def _plain(value: Any) -> Any:
    """Make ``value`` JSON-safe without importing models."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_plain(v) for v in value]
    return str(value)


def read_recent(limit: int = 100) -> list[dict]:
    """Return the most recent audit records (newest last)."""
    path = audit_log_path()
    if not os.path.isfile(path):
        return []
    with _WRITE_LOCK:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()[-max(1, limit):]
    out = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            logger.warning("skipping malformed audit line: %s", line[:120])
    return out
