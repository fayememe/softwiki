"""Local user table + group mapping + role resolution.

Authentication belongs to the external source; **authorization lives here**
(docs/02-design/auth-oidc.md §2, §4).

Flow for one request::

    ExternalIdentity  --upsert-->  LocalUser
                                   |
          mapping(external group -> role)   +  role_override
                                   |
                               granted role
                                   |
                    min(granted, session downgrade) = effective role

Roles are recomputed on **every** request rather than frozen at login, so that
editing a mapping takes effect immediately.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Iterable, List, Optional

import yaml

from softwiki.config import get_workspaces_root
from softwiki.identity.base import ExternalIdentity
from softwiki.permissions import (
    ALIASES,
    DEFAULT_ROLES,
    FALLBACK_ROLE,
    ROLE_ORDER,
    allowed_kbs,
    normalize_role,
    role_level,
)

logger = logging.getLogger(__name__)

#: What happens to an authenticated user who matches no mapping entry.
UNKNOWN_POLICIES = ("deny", "lowest", "pending")
DEFAULT_UNKNOWN_POLICY = "pending"

#: Scope value meaning "every kb, including ones created later".
WILDCARD = "*"

#: Single-machine mode uses the synthetic identity below: there is no external
#: source to ask, but the superuser still owns a row so that kb_scope, override
#: and the audit trail have something to point at.
LOCAL_ISSUER = "local:machine"
LOCAL_SUBJECT = "superuser"

USER_FILE_NAME = "users.yaml"
MAPPING_FILE_NAME = "identity.yaml"


class IdentityDenied(PermissionError):
    """The identity is authenticated but not allowed to use softwiki."""


@dataclass
class LocalUser:
    """One row of the local user table."""

    issuer: str
    subject: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    groups: List[str] = field(default_factory=list)
    kb_scope: object = WILDCARD
    role_override: Optional[str] = None
    # Which kb this user last opened. Remembered per user so switching is a
    # preference, not a process-wide side effect.
    active_kb: Optional[str] = None
    # Only for the built-in admin account (scrypt hash). External identities
    # never carry a password: the provider owns authentication.
    password_hash: Optional[str] = None
    is_active: bool = True
    created_at: Optional[str] = None
    last_login_at: Optional[str] = None

    @property
    def key(self) -> tuple[str, str]:
        return (self.issuer, self.subject)

    @property
    def identity(self) -> str:
        """Stable printable identity used in audit records."""
        return f"{self.issuer}:{self.subject}"

    def to_dict(self) -> dict:
        return {
            "issuer": self.issuer,
            "subject": self.subject,
            "email": self.email,
            "display_name": self.display_name,
            "groups": list(self.groups),
            "kb_scope": self.kb_scope,
            "role_override": self.role_override,
            "active_kb": self.active_kb,
            "password_hash": self.password_hash,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "last_login_at": self.last_login_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LocalUser":
        return cls(
            issuer=str(data["issuer"]),
            subject=str(data["subject"]),
            email=data.get("email"),
            display_name=data.get("display_name"),
            groups=[str(g) for g in (data.get("groups") or [])],
            kb_scope=data.get("kb_scope", WILDCARD),
            role_override=data.get("role_override"),
            active_kb=data.get("active_kb"),
            password_hash=data.get("password_hash"),
            is_active=bool(data.get("is_active", True)),
            created_at=data.get("created_at"),
            last_login_at=data.get("last_login_at"),
        )


@dataclass
class Authorization:
    """The resolved answer for one caller."""

    user: Optional[LocalUser]
    granted_role: str
    kb_scope: object = WILDCARD
    pending: bool = False

    @property
    def identity(self) -> str:
        return self.user.identity if self.user else "anonymous"


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


# -- store ---------------------------------------------------------------


class UserStore:
    """YAML-backed local user table.

    YAML rather than a new SQL table because the workspace already keeps its
    configuration this way, an admin can diff it, and there is no migration to
    run on the trial hosts. Swap ``load``/``save`` for a table later without
    touching the resolution logic.
    """

    def __init__(self, path: Optional[str] = None):
        self.path = path

    # -- locations -------------------------------------------------------

    def _file(self) -> str:
        if self.path:
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
            return os.path.abspath(self.path)
        root = os.path.join(get_workspaces_root(), "config")
        os.makedirs(root, exist_ok=True)
        return os.path.join(root, USER_FILE_NAME)

    def _mapping_file(self) -> str:
        root = os.path.join(get_workspaces_root(), "config")
        os.makedirs(root, exist_ok=True)
        return os.path.join(root, MAPPING_FILE_NAME)

    # -- users -----------------------------------------------------------

    def load(self) -> List[LocalUser]:
        path = self._file()
        if not os.path.isfile(path):
            return []
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception as exc:  # noqa: BLE001 - a broken table must not crash requests
            logger.error("ignoring unreadable %s: %s", path, exc)
            return []
        rows = data.get("users") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            logger.error("%s: expected a list of users, got %r", path, type(rows))
            return []
        users = []
        for row in rows:
            if not isinstance(row, dict):
                logger.warning("skipping malformed user row: %r", row)
                continue
            try:
                users.append(LocalUser.from_dict(row))
            except (KeyError, TypeError) as exc:
                logger.warning("skipping user row %r: %s", row, exc)
        return users

    def save(self, users: Iterable[LocalUser]) -> None:
        path = self._file()
        payload = {"users": [u.to_dict() for u in users]}
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            yaml.safe_dump(payload, f, allow_unicode=True, sort_keys=False)
        os.replace(tmp, path)

    def find(self, issuer: str, subject: str) -> Optional[LocalUser]:
        for user in self.load():
            if user.issuer == issuer and user.subject == subject:
                return user
        return None

    def upsert(self, identity: ExternalIdentity) -> LocalUser:
        """Insert or refresh a user after a successful sign-in."""
        users = self.load()
        now = _now()
        for index, user in enumerate(users):
            if user.key == identity.key:
                user.email = identity.email or user.email
                user.display_name = identity.display_name or user.display_name
                if identity.groups:
                    user.groups = list(identity.groups)
                user.last_login_at = now
                users[index] = user
                self.save(users)
                return user

        user = LocalUser(
            issuer=identity.issuer,
            subject=identity.subject,
            email=identity.email,
            display_name=identity.display_name,
            groups=list(identity.groups),
            kb_scope=WILDCARD,
            created_at=now,
            last_login_at=now,
        )
        users.append(user)
        self.save(users)
        return user

    def update(self, issuer: str, subject: str, **changes) -> LocalUser:
        users = self.load()
        for user in users:
            if user.key == (issuer, subject):
                for name, value in changes.items():
                    if not hasattr(user, name):
                        raise AttributeError(f"no such user field: {name}")
                    setattr(user, name, value)
                # save() writes the list we are iterating, so the edited row is
                # what lands on disk — no re-read in between.
                self.save(users)
                return user
        raise KeyError(f"no such user: {issuer}:{subject}")

    # -- mapping ---------------------------------------------------------

    def mapping(self) -> Dict[str, list[str]]:
        """Return ``{external_group: [role, ...]}``."""
        path = self._mapping_file()
        if not os.path.isfile(path):
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception as exc:  # noqa: BLE001
            logger.error("ignoring unreadable %s: %s", path, exc)
            return {}
        raw = data.get("groups") if isinstance(data, dict) else {}
        if not isinstance(raw, dict):
            logger.error("%s: 'groups' must be a mapping", path)
            return {}
        out: Dict[str, list[str]] = {}
        for group, roles in raw.items():
            if isinstance(roles, str):
                roles = [roles]
            if not isinstance(roles, (list, tuple)):
                logger.warning("ignoring mapping %r with non-list value %r", group, roles)
                continue
            normalised = []
            for role in roles:
                text = str(role).strip()
                name = normalize_role(text)
                if text not in ROLE_ORDER and text not in ALIASES:
                    # A typo lands the group on the lowest role; say so loudly
                    # so an operator can spot it without it breaking anything.
                    logger.warning(
                        "unknown role %r in mapping for group %r (treated as %s)",
                        role,
                        group,
                        name,
                    )
                normalised.append(name)
            out[str(group)] = normalised
        return out

    def save_mapping(self, mapping: Dict[str, list[str]]) -> None:
        path = self._mapping_file()
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            yaml.safe_dump({"groups": mapping}, f, allow_unicode=True, sort_keys=False)
        os.replace(tmp, path)

    def unknown_policy(self) -> str:
        value = (os.getenv("SOFTWIKI_UNKNOWN_USER_POLICY") or DEFAULT_UNKNOWN_POLICY).strip().lower()
        if value not in UNKNOWN_POLICIES:
            logger.warning(
                "unknown SOFTWIKI_UNKNOWN_USER_POLICY=%r, using %s",
                value,
                DEFAULT_UNKNOWN_POLICY,
            )
            return DEFAULT_UNKNOWN_POLICY
        return value

    # -- role resolution -------------------------------------------------

    def role_for(self, user: LocalUser) -> tuple[str, bool]:
        """Resolve ``(role, pending)`` for a user. Highest mapping wins."""
        if user.role_override:
            override = normalize_role(user.role_override)
            return override, False

        mapping = self.mapping()
        roles: list[str] = []
        for group in user.groups:
            roles.extend(mapping.get(group, []))
        if roles:
            return max(roles, key=role_level), False

        policy = self.unknown_policy()
        if policy == "lowest":
            return FALLBACK_ROLE, False
        if policy == "deny":
            return FALLBACK_ROLE, True
        return FALLBACK_ROLE, True  # pending

    def authorize(self, identity: ExternalIdentity) -> Authorization:
        """Resolve an identity into a role, raising when it must be refused."""
        user = self.upsert(identity)
        return self.authorize_user(user)

    def authorize_user(self, user: LocalUser) -> Authorization:
        """Resolve an existing local user, without touching sign-in bookkeeping."""
        if not user.is_active:
            raise IdentityDenied(f"user {user.identity} is disabled locally")

        role, pending = self.role_for(user)
        policy = self.unknown_policy()
        if pending and policy == "deny":
            raise IdentityDenied(f"user {user.identity} is not mapped to any role")

        return Authorization(
            user=user,
            granted_role=role,
            kb_scope=user.kb_scope,
            pending=pending,
        )

    def ensure_superuser_row(self) -> LocalUser:
        """Create the synthetic superuser row for single-machine mode if absent."""
        existing = self.find(LOCAL_ISSUER, LOCAL_SUBJECT)
        if existing:
            return existing
        users = self.load()
        user = LocalUser(
            issuer=LOCAL_ISSUER,
            subject=LOCAL_SUBJECT,
            display_name="superuser (single-machine mode)",
            groups=[],
            kb_scope=WILDCARD,
            role_override=ROLE_ORDER[-1],
            is_active=True,
            created_at=_now(),
        )
        users.append(user)
        self.save(users)
        return user


# -- kb visibility -------------------------------------------------------


def visible_kbs(scope, all_kbs: Iterable[str]) -> List[str]:
    """Resolve a stored ``kb_scope`` against the kb names that exist now."""
    return allowed_kbs(scope, all_kbs)


def kb_scope_is_empty(scope, all_kbs: Iterable[str]) -> bool:
    """True when a scope resolves to nothing.

    Used by the admin page to surface "this user can see 0 kbs" — a typo
    should be visible without being a hard error.
    """
    if scope is None:
        return False
    names = list(all_kbs)
    if not names:
        return False
    return not visible_kbs(scope, names)


# -- current user context ------------------------------------------------


@dataclass
class UserContext:
    """Per-request identity context, carried in a ContextVar."""

    identity: Optional[ExternalIdentity] = None
    authorization: Optional[Authorization] = None
    source_ip: Optional[str] = None

    @property
    def actor(self) -> dict:
        from softwiki.permissions import current_role

        if self.authorization and self.authorization.user:
            user = self.authorization.user
            return {
                "mode": os.getenv("SOFTWIKI_AUTH_MODE", "off"),
                "identity": user.identity,
                "role": current_role(),
                "source_ip": self.source_ip,
            }
        return {
            "mode": os.getenv("SOFTWIKI_AUTH_MODE", "off"),
            "identity": "superuser",
            "role": current_role(),
            "source_ip": self.source_ip,
        }


def dumps_scopes(scopes: Iterable[str]) -> str:
    return json.dumps(list(scopes), ensure_ascii=False)


__all__ = [
    "Authorization",
    "DEFAULT_ROLES",
    "IdentityDenied",
    "LOCAL_ISSUER",
    "LOCAL_SUBJECT",
    "LocalUser",
    "ROLE_ORDER",
    "UNKNOWN_POLICIES",
    "UserContext",
    "UserStore",
    "WILDCARD",
    "kb_scope_is_empty",
    "visible_kbs",
]
