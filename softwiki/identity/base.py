"""Identity sources: the "plug anything in" layer.

We do not run a user system. A source proves *who somebody is*; authorization
stays here (docs/02-design/auth-oidc.md §1).

Every source, whatever it speaks, produces the same :class:`ExternalIdentity`:

    (issuer, subject)  + optional email / display_name / groups

``issuer`` and ``subject`` are jointly unique. WeChat's ``openid`` differs per
application, so a bare subject would collide across sources.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Protocol, Type

logger = logging.getLogger(__name__)


@dataclass
class ExternalIdentity:
    """What a source tells us about a caller. Nothing about permissions."""

    issuer: str
    subject: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    groups: List[str] = field(default_factory=list)
    attributes: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.issuer = (self.issuer or "").strip()
        self.subject = (self.subject or "").strip()
        if not self.issuer or not self.subject:
            raise ValueError("identity needs both issuer and subject")
        self.groups = [str(g) for g in (self.groups or [])]

    @property
    def key(self) -> tuple[str, str]:
        return (self.issuer, self.subject)


class IdentityAdapter(Protocol):
    """One way of turning a provider response into an :class:`ExternalIdentity`."""

    name: str

    def identity_from_claims(self, issuer: str, claims: Mapping) -> ExternalIdentity:
        """Convert already-verified claims (OIDC) into an identity."""

    def fetch_identity(self, issuer: str, code: str, **options) -> ExternalIdentity:
        """Exchange an authorization code for an identity (non-standard flows)."""


_ADAPTERS: Dict[str, Type] = {}


def register_adapter(cls: Type) -> Type:
    name = getattr(cls, "name", "")
    if not name:
        raise ValueError(f"{cls!r} needs a name")
    _ADAPTERS[name] = cls
    return cls


def available_adapters() -> List[str]:
    _load_builtin()
    return sorted(_ADAPTERS)


def get_adapter(name: str) -> IdentityAdapter:
    _load_builtin()
    try:
        cls = _ADAPTERS[name]
    except KeyError:
        raise KeyError(
            f"unknown identity adapter {name!r}; available: {sorted(_ADAPTERS)}"
        ) from None
    return cls()


_LOADED = False


def _load_builtin() -> None:
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    from softwiki.identity import oidc, wechat  # noqa: F401 - registration side effect
