"""Identity from a reverse proxy (forward-auth).

The proxy does the OIDC dance (state/nonce/PKCE/JWKS/refresh) and, once the
user is signed in, injects headers such as ``X-Auth-Request-User``. We only
read those headers.

Security model — the whole thing rests on this:

1. **Only trusted peers are believed.** Headers are honoured exclusively when
   the TCP peer is listed in ``SOFTWIKI_TRUSTED_PROXIES`` (CIDRs or IPs).
   ``X-Forwarded-For`` is never consulted: it is client-controlled. A caller
   connecting directly to the app cannot forge an identity.
2. **The proxy must strip client-supplied copies** of these headers. Anything
   that reaches the app comes from the proxy.
3. There is **no local session cookie** in this mode: the proxy owns the
   session, so identity is re-derived on every request. That also means a
   proxy logout is effective immediately.

Configuration::

    SOFTWIKI_AUTH_MODE=proxy
    SOFTWIKI_TRUSTED_PROXIES=172.16.0.0/12,127.0.0.1
    SOFTWIKI_PROXY_USER_HEADER=X-Auth-Request-User        # required
    SOFTWIKI_PROXY_GROUPS_HEADER=X-Auth-Request-Groups    # optional
    SOFTWIKI_PROXY_EMAIL_HEADER=X-Auth-Request-Email      # optional
    SOFTWIKI_PROXY_NAME_HEADER=X-Auth-Request-Preferred-Username
    SOFTWIKI_PROXY_ISSUER_LABEL=campus                    # optional
"""

from __future__ import annotations

import ipaddress
import os
from functools import lru_cache
from typing import Iterable, Optional

from softwiki.identity.base import ExternalIdentity

DEFAULT_USER_HEADER = "X-Auth-Request-User"
DEFAULT_GROUPS_HEADER = "X-Auth-Request-Groups"
DEFAULT_EMAIL_HEADER = "X-Auth-Request-Email"
DEFAULT_NAME_HEADER = "X-Auth-Request-Preferred-Username"


def _parse_networks(spec: str) -> tuple[tuple, frozenset, Optional[str]]:
    """Split a spec into (CIDR networks, literal peer names, error).

    A literal name (no slash) that is not an IP is kept for exact matching:
    test clients and unix-socket peers report names rather than addresses.
    """
    networks = []
    literals: set[str] = set()
    for raw in (spec or "").split(","):
        item = raw.strip()
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
            continue
        except ValueError:
            pass
        if "/" in item:
            return tuple(networks), frozenset(literals), f"invalid entry: {item}"
        literals.add(item)
    return tuple(networks), frozenset(literals), None


@lru_cache(maxsize=8)
def _cached(spec: str):
    return _parse_networks(spec)


def trusted_spec() -> str:
    return os.getenv("SOFTWIKI_TRUSTED_PROXIES", "").strip()


def peer_trusted(peer: Optional[str]) -> bool:
    """Is `peer` a reverse proxy we believe?

    Fail closed: an empty or malformed list trusts nobody.
    """
    if not peer:
        return False
    spec = trusted_spec()
    if not spec:
        return False
    networks, literals, error = _cached(spec)
    if error is not None:
        return False
    if peer in literals:
        return True
    try:
        addr = ipaddress.ip_address(peer)
    except ValueError:
        return False
    if getattr(addr, "ipv4_mapped", None):
        addr = addr.ipv4_mapped
    return any(addr.version == n.version and addr in n for n in networks)


def _header(headers, name: str) -> Optional[str]:
    """Read a header case-insensitively.

    Starlette's ``Headers`` already ignore case; plain mappings (tests, ASGI
    scope dicts) do not. Normalising here avoids a config that works behind one
    proxy and silently fails behind another.
    """
    value = headers.get(name)
    if value is None:
        lowered = name.lower()
        for key, candidate in headers.items():
            if str(key).lower() == lowered:
                value = candidate
                break
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _split_groups(value: Optional[str]) -> list[str]:
    if not value:
        return []
    for sep in (";", ","):
        value = value.replace(sep, " ")
    return sorted({g for g in value.split() if g})


def identity_from_headers(headers, peer: Optional[str]) -> Optional[ExternalIdentity]:
    """Build an identity from proxy headers, or None when the peer is untrusted.

    Returning None (rather than raising) lets the caller answer "not
    authenticated" — the safe answer — without leaking why.
    """
    if not peer_trusted(peer):
        return None

    user = _header(headers, os.getenv("SOFTWIKI_PROXY_USER_HEADER", DEFAULT_USER_HEADER))
    if not user:
        return None

    label = os.getenv("SOFTWIKI_PROXY_ISSUER_LABEL", "proxy")
    groups = _split_groups(
        _header(headers, os.getenv("SOFTWIKI_PROXY_GROUPS_HEADER", DEFAULT_GROUPS_HEADER))
    )
    email = _header(headers, os.getenv("SOFTWIKI_PROXY_EMAIL_HEADER", DEFAULT_EMAIL_HEADER))
    name = _header(headers, os.getenv("SOFTWIKI_PROXY_NAME_HEADER", DEFAULT_NAME_HEADER))

    return ExternalIdentity(
        issuer=f"proxy:{label}",
        subject=user,
        email=email,
        display_name=name or email or user,
        groups=groups,
        attributes={"peer": peer or ""},
    )


def client_ip_for_audit(peer: Optional[str], forwarded_for: Optional[str]) -> Optional[str]:
    """The address to record and rate-limit on.

    Behind a reverse proxy the TCP peer is the proxy itself. The forwarded
    address is trustworthy only when that peer is in ``SOFTWIKI_TRUSTED_PROXIES``
    — the same boundary that guards identity headers. Never use this for
    "is the caller local" decisions; those must stay on the TCP peer.
    """
    if not peer:
        return None
    if not forwarded_for or not peer_trusted(peer):
        return peer
    first = forwarded_for.split(",")[0].strip()
    return first or peer


def describe() -> dict:
    """Diagnostics: what we would trust, without revealing identities."""
    networks, literals, error = _parse_networks(trusted_spec())
    return {
        "trusted_proxies": [*[str(n) for n in networks], *sorted(literals)],
        "trusted_error": error,
        "user_header": os.getenv("SOFTWIKI_PROXY_USER_HEADER", DEFAULT_USER_HEADER),
        "groups_header": os.getenv("SOFTWIKI_PROXY_GROUPS_HEADER", DEFAULT_GROUPS_HEADER),
        "enabled": bool(networks) and error is None,
    }
