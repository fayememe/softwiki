"""Role/capability policy for single-window team trial.

No accounts, no keys yet: a client declares a role via Web cookie or
X-SoftWiki-Role header. This is a trust-based convenience boundary, not an
authentication boundary.
"""
from __future__ import annotations

import fnmatch
import os
from contextvars import ContextVar
from typing import Iterable

import yaml

from softwiki.config import get_config_path

_ROLE_CTX: ContextVar[str | None] = ContextVar("softwiki_role", default=None)

ALIASES = {
    "study": "wiki-study",
    "work": "wiki-work",
    "manage": "wiki-manage",
    "admin": "wiki-admin",
    "user": "wiki-study",
    "wiki-user": "wiki-study",
    "wiki-research": "wiki-study",
}

DEFAULT_ROLES = {
    "wiki-study": [
        "read.*",
    ],
    "wiki-work": [
        "read.*",
        "wiki.build",
        "wiki.preview",
        "wiki.submit",
    ],
    "wiki-manage": [
        "read.*",
        "wiki.build",
        "wiki.preview",
        "wiki.apply",
        "ingest.write",
        "index.write",
        "document.delete",
        "conflict.adjudicate",
        "nli.scan",
    ],
    "wiki-admin": ["*"],
}


def normalize_role(role: str | None) -> str:
    role = (role or "").strip()
    role = ALIASES.get(role, role)
    if role in DEFAULT_ROLES:
        return role
    return "wiki-admin"


def _load_policy() -> dict:
    """Load workspace permissions.yaml if present; otherwise defaults."""
    path = get_config_path("permissions.yaml")
    if not path or not os.path.exists(path):
        return {"roles": DEFAULT_ROLES}
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        roles = data.get("roles")
        if isinstance(roles, dict) and roles:
            merged = dict(DEFAULT_ROLES)
            for name, cfg in roles.items():
                if isinstance(cfg, list):
                    merged[normalize_role(name)] = [str(x) for x in cfg]
                elif isinstance(cfg, dict):
                    allow = [str(x) for x in (cfg.get("allow") or [])]
                    deny = [str(x) for x in (cfg.get("deny") or [])]
                    merged[normalize_role(name)] = [x for x in allow if x not in deny]
            return {"roles": merged}
    except Exception:
        pass
    return {"roles": DEFAULT_ROLES}


def role_capabilities(role: str | None = None) -> list[str]:
    role = normalize_role(role or current_role())
    return list(_load_policy().get("roles", {}).get(role, []))


def can(capability: str, role: str | None = None) -> bool:
    role = normalize_role(role or current_role())
    caps = role_capabilities(role)
    if "*" in caps:
        return True
    for cap in caps:
        if cap == capability:
            return True
        if cap.endswith(".*") and capability.startswith(cap[:-1]):
            return True
        if fnmatch.fnmatch(capability, cap):
            return True
    return False


def current_role() -> str:
    ctx = _ROLE_CTX.get()
    if ctx:
        return normalize_role(ctx)
    return normalize_role(os.getenv("SOFTWIKI_ROLE") or os.getenv("SOFTWIKI_MODE") or "wiki-admin")


def set_role(role: str | None):
    return _ROLE_CTX.set(normalize_role(role))


def reset_role(token) -> None:
    _ROLE_CTX.reset(token)
