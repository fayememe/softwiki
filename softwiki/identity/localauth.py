"""Password login for the built-in admin account.

Why this exists: an installation needs one way in before any external identity
provider is wired up (and a way back in when that provider is down). It is an
**escape hatch**, not a user system — every other account still comes from the
provider.

Rules, in order of importance:

1. **No default password.** If ``SOFTWIKI_ADMIN_PASSWORD`` is not set on first
   start, a random one is generated and printed once. Nothing ships with
   ``admin/admin``.
2. **Only a hash is stored** (scrypt + per-password salt). Plaintext never
   touches disk.
3. **Rate limited.** Password login is the only guessable entry point, so it is
   throttled per peer address.
4. **Audited**, like every other authentication attempt.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict, deque
from typing import Optional

from softwiki.identity.users import LocalUser, UserStore

ISSUER = "local:builtin"
SUBJECT = "admin"

# scrypt parameters: n=2^14 is ~16 MB and a few ms per hash on a small VPS.
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_DKLEN = 32


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("password must not be empty")
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_DKLEN
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(derived)}"


def verify_password(password: str, stored: Optional[str]) -> bool:
    """Constant-time check. A malformed hash verifies nothing."""
    if not password or not stored:
        return False
    try:
        scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_unb64(salt_b64),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(_unb64(hash_b64)),
        )
        return hmac.compare_digest(derived, _unb64(hash_b64))
    except (ValueError, TypeError):
        return False


def _random_password() -> str:
    # Long enough to survive being pasted into a terminal, short enough to type.
    return secrets.token_urlsafe(18)


def builtin_admin(store: Optional[UserStore] = None) -> Optional[LocalUser]:
    store = store or UserStore()
    return store.find(ISSUER, SUBJECT)


def set_builtin_admin_password(password: str, store: Optional[UserStore] = None) -> LocalUser:
    """Create or update the built-in admin. Always role ``wiki-admin``."""
    if len(password) < 12:
        raise ValueError("password must be at least 12 characters")
    store = store or UserStore()
    users = store.load()
    existing = next((u for u in users if u.key == (ISSUER, SUBJECT)), None)
    digest = hash_password(password)
    if existing is None:
        admin = LocalUser(
            issuer=ISSUER,
            subject=SUBJECT,
            display_name="Built-in administrator",
            role_override="wiki-admin",
            kb_scope="*",
            password_hash=digest,
            is_active=True,
            created_at=_now(),
        )
        users.append(admin)
    else:
        existing.password_hash = digest
        existing.role_override = "wiki-admin"
        existing.is_active = True
        admin = existing
    store.save(users)
    return admin


def ensure_builtin_admin(store: Optional[UserStore] = None) -> tuple[bool, Optional[str]]:
    """Create the admin on first start.

    Returns ``(created, password)`` where ``password`` is the plaintext to show
    the operator **once** when it was generated (None when a password already
    existed or was supplied by the environment).
    """
    store = store or UserStore()
    if builtin_admin(store) is not None:
        return False, None

    supplied = (os.getenv("SOFTWIKI_ADMIN_PASSWORD") or "").strip()
    if supplied:
        set_builtin_admin_password(supplied, store)
        return True, None

    generated = _random_password()
    set_builtin_admin_password(generated, store)
    return True, generated


def _now() -> str:
    from datetime import datetime

    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


# --------------------------------------------------------------------------- #
# Rate limiting
# --------------------------------------------------------------------------- #

class LoginRateLimiter:
    """Sliding window per peer address.

    In-process: enough for a single-instance deployment, which is what we ship.
    Behind multiple workers this becomes per-worker; the limit then multiplies,
    so keep it conservative.
    """

    def __init__(self, attempts: int = 5, window_seconds: int = 60):
        self.attempts = attempts
        self.window = window_seconds
        self._events: dict[str, deque] = defaultdict(deque)

    def allow(self, peer: Optional[str]) -> bool:
        key = peer or "unknown"
        now = time.monotonic()
        events = self._events[key]
        while events and now - events[0] > self.window:
            events.popleft()
        if len(events) >= self.attempts:
            return False
        events.append(now)
        return True

    def reset(self) -> None:
        self._events.clear()


LOGIN_LIMITER = LoginRateLimiter()


def authenticate(username: str, password: str, store: Optional[UserStore] = None) -> Optional[LocalUser]:
    """Verify the built-in admin credentials. Returns the user or None.

    Deliberately ignores any other account: external identities have no
    password here, and treating them as password users would be a back door.
    """
    store = store or UserStore()
    admin = builtin_admin(store)
    if admin is None or not admin.is_active:
        return None
    if username.strip().lower() not in ("admin", SUBJECT):
        return None
    if not verify_password(password, admin.password_hash):
        return None
    admin.last_login_at = _now()
    users = [u for u in store.load() if u.key != admin.key]
    users.append(admin)
    store.save(users)
    return admin
