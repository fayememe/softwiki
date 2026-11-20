"""Standard OIDC adapter.

Configuration only — there is no protocol code here beyond claim parsing, since
a standard OIDC provider already returns verified claims.
"""
from __future__ import annotations

import logging
from typing import Mapping

from softwiki.identity.base import ExternalIdentity, register_adapter

logger = logging.getLogger(__name__)

#: Claims we look at, in order of preference.
SUBJECT_CLAIMS = ("sub",)
GROUP_CLAIMS = ("groups", "roles", "memberOf", "group")


@register_adapter
class OidcAdapter:
    name = "oidc"

    def identity_from_claims(self, issuer: str, claims: Mapping) -> ExternalIdentity:
        subject = ""
        for claim in SUBJECT_CLAIMS:
            value = claims.get(claim)
            if value:
                subject = str(value)
                break
        if not subject:
            raise ValueError("OIDC claims carry no 'sub'")

        # First group-ish claim that carries anything wins; provider naming varies.
        groups = []
        for claim in GROUP_CLAIMS:
            value = claims.get(claim)
            if isinstance(value, str):
                groups.extend([g for g in value.replace(",", " ").split() if g])
            elif isinstance(value, (list, tuple, set)):
                groups.extend([str(g) for g in value if g])
            if groups:
                break

        attributes = {
            k: str(v)
            for k, v in claims.items()
            if k not in ("email", "name", "preferred_username", *GROUP_CLAIMS)
            and isinstance(v, (str, int, float, bool))
        }
        return ExternalIdentity(
            issuer=issuer,
            subject=subject,
            email=claims.get("email"),
            display_name=(
                claims.get("name")
                or claims.get("preferred_username")
                or claims.get("email")
            ),
            groups=sorted(set(groups)),
            attributes=attributes,
        )

    def fetch_identity(self, issuer: str, code: str, **options) -> ExternalIdentity:
        raise NotImplementedError(
            "standard OIDC identities arrive as verified claims; "
            "the token exchange belongs to the provider client configuration"
        )
