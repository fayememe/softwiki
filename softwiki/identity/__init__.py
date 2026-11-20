"""Identity and authorization (docs/02-design/auth-oidc.md).

We do not run a user system. This package consumes identities from external
sources and decides what they may do here.
"""
from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Optional

from softwiki.identity.base import (
    ExternalIdentity,
    available_adapters,
    get_adapter,
    register_adapter,
)
from softwiki.identity.superuser import (
    SuperuserDenied,
    SuperuserSession,
    auth_mode,
    check_reauth,
    close_superuser,
    is_local_address,
    open_superuser,
    superuser_session,
)
from softwiki.identity.users import (
    Authorization,
    IdentityDenied,
    LocalUser,
    UserStore,
)

logger = logging.getLogger(__name__)

CONTEXT: ContextVar[Optional["RequestIdentity"]] = ContextVar(
    "softwiki_identity", default=None
)


class RequestIdentity:
    """Everything the auth layer learned about one request."""

    __slots__ = ("authorization", "source_ip", "superuser", "authenticated")

    def __init__(
        self,
        authorization: Optional[Authorization] = None,
        source_ip: Optional[str] = None,
        superuser: bool = False,
        authenticated: bool = False,
    ):
        self.authorization = authorization
        self.source_ip = source_ip
        self.superuser = superuser
        self.authenticated = authenticated

    @property
    def role(self) -> str:
        if self.authorization:
            return self.authorization.granted_role
        from softwiki.permissions import ROLE_ORDER

        return ROLE_ORDER[-1] if self.superuser else "wiki-study"

    @property
    def identity(self) -> str:
        if self.authorization and self.authorization.user:
            return self.authorization.user.identity
        return "superuser" if self.superuser else "anonymous"

    @property
    def kb_scope(self):
        if self.authorization:
            return self.authorization.kb_scope
        return "*"

    def actor(self) -> dict:
        from softwiki.permissions import current_role

        return {
            "mode": auth_mode(),
            "identity": self.identity,
            "role": current_role(),
            "source_ip": self.source_ip,
        }


def set_context(identity: Optional[RequestIdentity]):
    return CONTEXT.set(identity)


def reset_context(token) -> None:
    CONTEXT.reset(token)


def current_identity() -> Optional[RequestIdentity]:
    return CONTEXT.get()


__all__ = [
    "Authorization",
    "ExternalIdentity",
    "IdentityDenied",
    "LocalUser",
    "RequestIdentity",
    "SuperuserDenied",
    "SuperuserSession",
    "UserStore",
    "auth_mode",
    "available_adapters",
    "check_reauth",
    "close_superuser",
    "current_identity",
    "get_adapter",
    "is_local_address",
    "open_superuser",
    "register_adapter",
    "reset_context",
    "set_context",
    "superuser_session",
]
