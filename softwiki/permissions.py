"""Role/capability policy.

Two layers (see docs/02-design/auth-oidc.md):

* **固有角色 (granted role)** — what the identity layer decided for this caller.
  Comes from an authenticated user (mapping + override), or from the
  single-machine mode where there is no identity system at all.
* **有效角色 (effective role)** — ``min(granted, session downgrade)``. A
  higher role may deliberately *work as* a lower one; a lower role can never
  escalate.

Everything here fails closed: an unknown role, an unreadable policy file or a
missing identity falls back to ``wiki-study`` (read-only), never to admin.
"""
from __future__ import annotations

import fnmatch
import logging
import os
from contextvars import ContextVar
from typing import Iterable

import yaml

from softwiki.config import get_config_path

logger = logging.getLogger(__name__)

# Granted role for the current request/tool call.
_ROLE_CTX: ContextVar[str | None] = ContextVar("softwiki_role", default=None)
# Requested downgrade for the current request/tool call (one level below).
_DOWNGRADE_CTX: ContextVar[str | None] = ContextVar("softwiki_downgrade", default=None)

# Ordered from least to most privileged. Position is the level.
ROLE_ORDER = ("wiki-study", "wiki-work", "wiki-manage", "wiki-admin")

#: Least privileged role. Every unknown input collapses to this one.
FALLBACK_ROLE = "wiki-study"

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
        "kb.create",
    ],
    "wiki-admin": ["*"],
}

#: Capabilities that need a fresh re-authentication even for an admin, and that
#: always land in the audit log (docs/02-design/auth-oidc.md §5, §7).
SENSITIVE_CAPABILITIES = frozenset({
    "system.admin",
    "kb.unregister",
    "permissions.write",
    "superuser.use",
})
def role_level(role: str | None) -> int:
    """Numeric level of a normalised role. Unknown roles are level 0."""
    try:
        return ROLE_ORDER.index(role or "")
    except ValueError:
        return 0


def normalize_role(role: str | None) -> str:
    """Normalise a role name, failing closed to :data:`FALLBACK_ROLE`.

    Unknown or misspelled names must never grant more than read-only access,
    otherwise a typo would silently promote a caller to administrator.
    """
    role = (role or "").strip()
    role = ALIASES.get(role, role)
    if role in DEFAULT_ROLES:
        return role
    if role:
        logger.warning("unknown role %r, falling back to %s", role, FALLBACK_ROLE)
    return FALLBACK_ROLE


def min_role(*roles: str | None) -> str:
    """Return the least privileged role among ``roles`` (downgrade semantics)."""
    candidates = [normalize_role(r) for r in roles if r]
    if not candidates:
        return FALLBACK_ROLE
    return min(candidates, key=role_level)


def _load_policy() -> dict:
    """Load workspace permissions.yaml if present; otherwise defaults."""
    path = get_config_path("permissions.yaml")
    if not path or not os.path.exists(path):
        return {"roles": DEFAULT_ROLES}
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as exc:  # noqa: BLE001 - bad policy must not crash requests
        logger.warning("ignoring unreadable permissions.yaml (%s): %s", path, exc)
        return {"roles": DEFAULT_ROLES}

    roles = data.get("roles")
    if not isinstance(roles, dict) or not roles:
        return {"roles": DEFAULT_ROLES}

    merged = dict(DEFAULT_ROLES)
    for name, cfg in roles.items():
        normalised = normalize_role(name)
        if isinstance(cfg, list):
            merged[normalised] = [str(x) for x in cfg]
        elif isinstance(cfg, dict):
            allow = [str(x) for x in (cfg.get("allow") or [])]
            deny = [str(x) for x in (cfg.get("deny") or [])]
            merged[normalised] = [x for x in allow if x not in deny]
        else:
            logger.warning("ignoring role %r with unexpected shape %r", name, type(cfg))
    return {"roles": merged}


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


def granted_role() -> str:
    """固有角色: the role this caller would have without any downgrade."""
    ctx = _ROLE_CTX.get()
    if ctx:
        return normalize_role(ctx)
    return normalize_role(os.getenv("SOFTWIKI_ROLE") or os.getenv("SOFTWIKI_MODE"))


def downgrade_role() -> str | None:
    """降级请求: the role this caller asked to work as, if any."""
    ctx = _DOWNGRADE_CTX.get()
    if ctx is not None:
        return normalize_role(ctx) if ctx else None
    env = os.getenv("SOFTWIKI_DOWNGRADE_ROLE")
    return normalize_role(env) if env else None


def current_role() -> str:
    """有效角色 = min(固有角色, 降级请求)."""
    granted = granted_role()
    requested = downgrade_role()
    return min_role(granted, requested) if requested else granted


def set_role(role: str | None):
    return _ROLE_CTX.set(normalize_role(role) if role else None)


def reset_role(token) -> None:
    _ROLE_CTX.reset(token)


def set_downgrade(role: str | None):
    """Request a downgrade. Never raises the granted role."""
    current = granted_role()
    requested = normalize_role(role) if role else None
    if requested and role_level(requested) > role_level(current):
        logger.warning(
            "ignoring downgrade %s from granted role %s (cannot escalate)",
            requested,
            current,
        )
        requested = current
    return _DOWNGRADE_CTX.set(requested)


def reset_downgrade(token) -> None:
    _DOWNGRADE_CTX.reset(token)


def is_sensitive(capability: str) -> bool:
    return capability in SENSITIVE_CAPABILITIES


def allowed_kbs(scope: Iterable[str] | str | None, all_kbs: Iterable[str]) -> list[str]:
    """Resolve a kb_scope value against the currently known kb names.

    ``None`` and ``"*"`` mean *all current and future* knowledge bases, so the
    wildcard expands to whatever exists right now. Unknown names simply do not
    match — a typo drops the kb from the list instead of raising.
    """
    names = sorted(all_kbs)
    if scope is None:
        return names
    if isinstance(scope, str):
        value = scope.strip()
        if value in ("", "*"):
            return names
        requested = [v.strip() for v in value.split(",") if v.strip()]
    else:
        requested = [str(v).strip() for v in scope]
    if "*" in requested:
        return names
    wanted = set(requested)
    return [n for n in names if n in wanted]
