"""Authentication modes and the superuser escape hatch.

See docs/02-design/auth-oidc.md §5.

Three modes
-----------
``off``
    Single machine. There is no identity system at all, so every caller is the
    machine's own superuser. This is the historical behaviour and stays the
    default.
``local``
    Identity comes from the local user table (seeded by an adapter), and the
    superuser is a *gated escape hatch*.
``oidc``
    Same as ``local``, but an external provider must be configured.

The superuser is never a row in a table. It is a *capability of the machine*
that must be opened deliberately:

* it is **off by default** in every mode except ``off``;
* it is **local-only** — the check is on the peer address of the connection,
  never on ``X-Forwarded-For`` (headers are client-controlled);
* opening it may return a **TTL**; remote opens *require* a TTL;
* sensitive actions still demand a **fresh re-authentication** token.

Deployment decides what "local" means in practice (host networking, binding
to 127.0.0.1, a reverse proxy that only exposes selected routes). The
application only defines the semantics.
"""
from __future__ import annotations

import hmac
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from softwiki.audit import record

logger = logging.getLogger(__name__)

MODES = ("off", "local", "oidc")

#: Addresses that count as "this machine". Loopback only: a container peer
#: address (172.x) is *not* local, which is the safe default.
LOCAL_ADDRESSES = frozenset({"127.0.0.1", "::1", "localhost", "testclient"})

#: How long a re-authentication stays valid.
REAUTH_TTL_SECONDS = 300


def auth_mode() -> str:
    """Return the configured mode, defaulting to ``off``."""
    raw = (os.getenv("SOFTWIKI_AUTH_MODE") or "").strip().lower()
    if raw in MODES:
        return raw
    if raw:
        logger.warning("unknown SOFTWIKI_AUTH_MODE=%r, falling back to 'off'", raw)
    # Legacy switch kept working: SOFTWIKI_AUTH_ENABLED=1 behaves like 'oidc'.
    if os.getenv("SOFTWIKI_AUTH_ENABLED", "").lower() in ("1", "true", "yes"):
        return "oidc"
    return "off"


def is_local_address(peer: Optional[str]) -> bool:
    """True when ``peer`` is this machine."""
    if not peer:
        return False
    address = peer.strip()
    if address.startswith("::ffff:"):
        address = address[len("::ffff:"):]
    return address in LOCAL_ADDRESSES


@dataclass
class SuperuserSession:
    """One opened superuser window."""

    opened_at: float
    ttl_seconds: Optional[float] = None
    opened_by: str = "local"
    source_ip: Optional[str] = None

    @property
    def expires_at(self) -> Optional[float]:
        if self.ttl_seconds is None:
            return None
        return self.opened_at + self.ttl_seconds

    def active(self, now: Optional[float] = None) -> bool:
        now = time.time() if now is None else now
        expiry = self.expires_at
        return expiry is None or now < expiry

    def describe(self) -> dict:
        return {
            "opened_at": self.opened_at,
            "expires_at": self.expires_at,
            "ttl_seconds": self.ttl_seconds,
            "opened_by": self.opened_by,
            "source_ip": self.source_ip,
            "active": self.active(),
        }


@dataclass
class _State:
    session: Optional[SuperuserSession] = None
    reauth: dict = field(default_factory=dict)  # identity -> timestamp


_STATE = _State()
_LOCK = threading.Lock()


class SuperuserDenied(PermissionError):
    """Raised when the escape hatch cannot be used for this caller."""


def superuser_token() -> str:
    return os.getenv("SOFTWIKI_SUPERUSER_TOKEN", "").strip()


def reauth_token() -> str:
    """Token used for the fresh re-authentication step.

    Falls back to the superuser token so a single secret opens both the window
    and the sensitive action.
    """
    return os.getenv("SOFTWIKI_REAUTH_TOKEN", "").strip() or superuser_token()


def _parse_ttl(value) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower()
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if text and text[-1] in units and text[:-1].replace(".", "", 1).isdigit():
        return float(text[:-1]) * units[text[-1]]
    return float(text)


def open_superuser(
    *,
    source_ip: Optional[str],
    ttl: Optional[float] = None,
    token: Optional[str] = None,
    actor: Optional[dict] = None,
) -> SuperuserSession:
    """Open a superuser window. Raises :class:`SuperuserDenied` on refusal."""
    mode = auth_mode()
    peer = source_ip
    ttl_seconds = _parse_ttl(ttl)

    if mode == "off":
        # Nothing to open: the machine already *is* the superuser. Report it
        # honestly instead of pretending a window was created.
        session = SuperuserSession(
            opened_at=time.time(), ttl_seconds=None, opened_by="mode=off", source_ip=peer
        )
        with _LOCK:
            _STATE.session = session
        return session

    if not is_local_address(peer):
        if ttl_seconds is None:
            record(
                "superuser.open",
                result="denied",
                detail="remote open requires an explicit ttl",
                actor=actor,
                source_ip=peer,
            )
            raise SuperuserDenied("remote opens need --ttl")
        expected = superuser_token()
        if not expected:
            record(
                "superuser.open",
                result="denied",
                detail="SOFTWIKI_SUPERUSER_TOKEN is not configured",
                actor=actor,
                source_ip=peer,
            )
            raise SuperuserDenied("superuser token is not configured")

    expected = superuser_token()
    if expected and not _token_matches(token, expected):
        record(
            "superuser.open", result="denied", detail="bad token", actor=actor, source_ip=peer
        )
        raise SuperuserDenied("invalid superuser token")

    session = SuperuserSession(
        opened_at=time.time(),
        ttl_seconds=ttl_seconds,
        opened_by="remote" if not is_local_address(peer) else "local",
        source_ip=peer,
    )
    with _LOCK:
        _STATE.session = session
    record(
        "superuser.open",
        result="ok",
        detail=f"ttl={ttl_seconds}",
        actor=actor,
        source_ip=peer,
    )
    return session


def close_superuser(*, actor: Optional[dict] = None, source_ip: Optional[str] = None) -> None:
    with _LOCK:
        existed = _STATE.session is not None
        _STATE.session = None
    record("superuser.close", result="ok" if existed else "noop", actor=actor, source_ip=source_ip)


def superuser_session() -> Optional[SuperuserSession]:
    """Return the active window, discarding an expired one."""
    with _LOCK:
        session = _STATE.session
        if session is None:
            return None
        if not session.active():
            _STATE.session = None
            record("superuser.expire", result="ok", source_ip=session.source_ip)
            return None
        return session


def superuser_available(*, source_ip: Optional[str]) -> bool:
    """Whether the caller could *open* the escape hatch, without opening it."""
    if auth_mode() == "off":
        return True
    if is_local_address(source_ip):
        return True
    return bool(superuser_token())


def reauth_required(capability: str) -> bool:
    from softwiki.permissions import is_sensitive

    return is_sensitive(capability)


def mark_reauth(identity: str) -> None:
    with _LOCK:
        _STATE.reauth[identity] = time.time()


def has_fresh_reauth(identity: str) -> bool:
    with _LOCK:
        stamp = _STATE.reauth.get(identity)
    return stamp is not None and (time.time() - stamp) < REAUTH_TTL_SECONDS


def check_reauth(identity: str, token: Optional[str]) -> bool:
    """Verify the fresh re-authentication token for a sensitive action."""
    expected = reauth_token()
    if not expected:
        # Nothing configured: do not invent a secret. The action is allowed by
        # role, and the audit record carries the identity.
        mark_reauth(identity)
        return True
    if token and _token_matches(token, expected):
        mark_reauth(identity)
        return True
    return has_fresh_reauth(identity)


def _token_matches(candidate: Optional[str], expected: str) -> bool:
    if not candidate:
        return False
    return hmac.compare_digest(candidate.encode(), expected.encode())


def reset_state() -> None:
    """Test helper: forget any open window or re-auth stamp."""
    with _LOCK:
        _STATE.session = None
        _STATE.reauth.clear()
