"""WeChat QR login adapter.

WeChat does **not** speak OIDC. The flow is its own OAuth2-flavoured one:

    qrconnect  -> code
    code       -> access_token (+ openid)   [sns/oauth2/access_token]
    openid     -> userinfo                  [sns/userinfo]

Two consequences worth stating up front:

* ``openid`` is scoped to one WeChat application, so it is only unique within
  this issuer. That is exactly why identities are keyed by
  ``(issuer, subject)``.
* WeChat has **no notion of school groups**. Every WeChat identity therefore
  arrives with no groups and lands in the ``pending`` bucket until an admin
  assigns a role. WeChat is an entry point for outside users, not a source of
  internal authority.

The module only parses what WeChat returns; the HTTP calls live in
:func:`fetch_identity` and are isolated so tests can stub them.
"""
from __future__ import annotations

import logging
import os
from typing import Mapping, Optional

from softwiki.identity.base import ExternalIdentity, register_adapter

logger = logging.getLogger(__name__)

AUTHORIZE_URL = "https://open.weixin.qq.com/connect/qrconnect"
TOKEN_URL = "https://api.weixin.qq.com/sns/oauth2/access_token"
USERINFO_URL = "https://api.weixin.qq.com/sns/userinfo"


@register_adapter
class WechatAdapter:
    name = "wechat"

    def identity_from_claims(self, issuer: str, claims: Mapping) -> ExternalIdentity:
        """Build an identity from an already-exchanged WeChat profile."""
        openid = claims.get("openid") or claims.get("unionid")
        if not openid:
            raise ValueError("WeChat profile carries no openid")
        return ExternalIdentity(
            issuer=issuer,
            subject=str(openid),
            display_name=claims.get("nickname"),
            groups=[],  # WeChat knows nothing about groups
            attributes={
                "unionid": str(claims.get("unionid") or ""),
                "country": str(claims.get("country") or ""),
                "province": str(claims.get("province") or ""),
                "city": str(claims.get("city") or ""),
                "source": "wechat",
            },
        )

    def authorize_url(self, app_id: str, redirect_uri: str, state: str) -> str:
        from urllib.parse import quote

        return (
            f"{AUTHORIZE_URL}?appid={quote(app_id)}"
            f"&redirect_uri={quote(redirect_uri, safe='')}"
            f"&response_type=code&scope=snsapi_login"
            f"&state={quote(state)}#wechat_redirect"
        )

    def fetch_identity(self, issuer: str, code: str, **options) -> ExternalIdentity:
        """Exchange ``code`` for an identity via WeChat's endpoints."""
        app_id = options.get("app_id") or os.getenv("WECHAT_APP_ID", "")
        secret = options.get("app_secret") or os.getenv("WECHAT_APP_SECRET", "")
        if not app_id or not secret:
            raise ValueError("WECHAT_APP_ID / WECHAT_APP_SECRET are not configured")

        token = self._token(app_id, secret, code)
        profile = self._userinfo(token["access_token"], token["openid"])
        profile.setdefault("openid", token["openid"])
        return self.identity_from_claims(issuer, profile)

    # -- transport ---------------------------------------------------------

    def _get(self, url: str, params: Mapping) -> dict:
        import httpx

        response = httpx.get(url, params=dict(params), timeout=10.0)
        response.raise_for_status()
        data = response.json()
        if data.get("errcode"):
            raise RuntimeError(
                f"WeChat error {data.get('errcode')}: {data.get('errmsg')}"
            )
        return data

    def _token(self, app_id: str, secret: str, code: str) -> dict:
        return self._get(
            TOKEN_URL,
            {
                "appid": app_id,
                "secret": secret,
                "code": code,
                "grant_type": "authorization_code",
            },
        )

    def _userinfo(self, access_token: str, openid: str) -> dict:
        return self._get(
            USERINFO_URL,
            {"access_token": access_token, "openid": openid, "lang": "zh_CN"},
        )
