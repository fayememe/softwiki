"""Source-address allowlist (network ACL).

This is a **perimeter**, not identity: it answers "may this peer talk to us at
all". It exists because an auth-less deployment (`SOFTWIKI_AUTH_MODE=off`) is
reachable by anyone who can open the port — IP restriction is the cheapest way
to shrink that surface before real authentication is in place.

It is not a substitute for auth: everyone inside an allowed range is still the
same principal.

Config
------
``SOFTWIKI_ALLOWED_CIDRS``
    Comma-separated CIDRs allowed to use the instance. **Empty means disabled**
    (backward compatible). Once set, every other peer is refused with 403 and
    an audit record.

``SOFTWIKI_TRUSTED_CIDRS``
    Peers that bypass the check. Defaults to loopback plus the private and
    container ranges, because:
      * healthchecks originate inside the container (127.0.0.1);
      * the web container proxies ``/api/*`` over the docker bridge;
      * Hermes/SWAgent call MCP from the host or docker network.
    On a locked-down deployment, narrow this list.

Fail-closed: a malformed allowlist refuses everyone rather than silently
allowing all. A typo must not open the instance.
"""

from __future__ import annotations

import ipaddress
import os
from functools import lru_cache
from typing import Iterable, Optional, Tuple

DEFAULT_TRUSTED = "127.0.0.0/8,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,fc00::/7"

# Names reported in the deny reason; kept short on purpose (it goes to clients).
_REASON_NO_MATCH = "source address not allowlisted"
_REASON_BAD_IP = "unknown source address"
_REASON_BAD_CONFIG = "allowlist misconfigured (deny all)"


def _parse(value: str) -> Tuple[Tuple, Optional[str]]:
    """Parse a CIDR list. Returns (networks, error)."""
    networks = []
    for raw in (value or "").split(","):
        item = raw.strip()
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            return tuple(networks), f"invalid CIDR: {item}"
    return tuple(networks), None


@lru_cache(maxsize=8)
def _allowed(spec: str) -> Tuple[Tuple, Optional[str]]:
    return _parse(spec)


@lru_cache(maxsize=8)
def _trusted(spec: str) -> Tuple[Tuple, Optional[str]]:
    return _parse(spec)


def allowed_spec() -> str:
    return os.getenv("SOFTWIKI_ALLOWED_CIDRS", "").strip()


def trusted_spec() -> str:
    return os.getenv("SOFTWIKI_TRUSTED_CIDRS", DEFAULT_TRUSTED).strip()


def enabled() -> bool:
    return bool(allowed_spec())


def _normalize(ip: str) -> Optional[ipaddress._BaseAddress]:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    # Docker and dual-stack sockets may hand us IPv4-mapped IPv6.
    if getattr(addr, "ipv4_mapped", None):
        return addr.ipv4_mapped
    return addr


def _match(addr, networks: Iterable) -> bool:
    return any(addr.version == n.version and addr in n for n in networks)


def check(ip: Optional[str]) -> Tuple[bool, Optional[str]]:
    """Decide whether `ip` may use this instance. Never raises."""
    if not enabled():
        return True, None
    if not ip:
        return False, _REASON_BAD_IP

    addr = _normalize(ip)
    if addr is None:
        return False, _REASON_BAD_IP

    trusted, trusted_err = _trusted(trusted_spec())
    if trusted_err is None and _match(addr, trusted):
        return True, None

    allowed, allowed_err = _allowed(allowed_spec())
    if allowed_err is not None:
        # Fail closed: a broken allowlist must not open the instance.
        return False, _REASON_BAD_CONFIG

    if _match(addr, allowed):
        return True, None
    return False, _REASON_NO_MATCH


def describe() -> dict:
    """Diagnostics for /api/status and tests."""
    allowed, allowed_err = _parse(allowed_spec())
    trusted, trusted_err = _parse(trusted_spec())
    return {
        "enabled": enabled(),
        "allowed": [str(n) for n in allowed],
        "trusted": [str(n) for n in trusted],
        "allowed_error": allowed_err,
        "trusted_error": trusted_err,
    }
