"""Verify that a softwiki deployment honours reverse-proxy identity headers.

This is the hand-over / acceptance tool: run it against the URL the *customer's*
proxy exposes. It answers one question — "do the headers you inject actually
become an identity here?" — without needing to know the customer's provider.

Usage:
    python3 scripts/verify_proxy_headers.py http://127.0.0.1:6200 \
        --user alice --groups staff

Exit codes:
    0  headers honoured (authenticated as the expected user)
    1  not honoured (anonymous) — proxy not connected, or peer not trusted
    2  cannot reach the server / not in proxy mode
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import urllib.error
import urllib.request


def _get(url: str, headers: dict, timeout: float = 10.0, insecure: bool = False):
    req = urllib.request.Request(url, headers=headers)
    context = ssl._create_unverified_context() if insecure else None
    with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
        return resp.status, json.load(resp)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("base", help="API base URL, e.g. http://127.0.0.1:6200")
    ap.add_argument("--user", default="proxy-check", help="value for the user header")
    ap.add_argument("--groups", default="", help="value for the groups header")
    ap.add_argument("--user-header", default="X-Auth-Request-User")
    ap.add_argument("--groups-header", default="X-Auth-Request-Groups")
    ap.add_argument("--insecure", action="store_true",
                    help="skip TLS verification (self-signed demo certificates)")
    args = ap.parse_args()

    base = args.base.rstrip("/")

    try:
        _, providers = _get(f"{base}/api/auth/providers", {}, insecure=args.insecure)
    except urllib.error.URLError as exc:
        print(f"FAIL cannot reach {base}: {exc}")
        return 2

    mode = providers.get("mode")
    print(f"mode: {mode}")
    if mode != "proxy":
        print(
            "FAIL this deployment is not in proxy mode "
            "(set SOFTWIKI_AUTH_MODE=proxy). Nothing to verify."
        )
        return 2

    proxy_info = providers.get("proxy") or {}
    print(f"trusted peers: {proxy_info.get('trusted_proxies') or '(none!)'}")
    print(f"user header:   {proxy_info.get('user_header')}")
    print(f"groups header: {proxy_info.get('groups_header')}")

    headers = {args.user_header: args.user}
    if args.groups:
        headers[args.groups_header] = args.groups

    try:
        _, me = _get(f"{base}/api/auth/me", headers, insecure=args.insecure)
    except urllib.error.URLError as exc:
        print(f"FAIL /api/auth/me: {exc}")
        return 2

    authenticated = bool(me.get("authenticated"))
    print(f"identity: {me.get('identity')}  role: {me.get('granted_role')}  "
          f"pending: {me.get('pending')}")

    if authenticated and args.user in str(me.get("identity", "")):
        print("OK  headers are honoured: the proxy identity reaches the app.")
        return 0

    print(
        "FAIL headers ignored. Checklist:\n"
        "  1. is the request coming from a peer listed in SOFTWIKI_TRUSTED_PROXIES?\n"
        "     (direct calls from a laptop are NOT the proxy — test through the proxy URL)\n"
        "  2. does your proxy actually set the header on the upstream request?\n"
        "     oauth2-proxy needs --set-xauthrequest=true\n"
        "  3. is the header name the one configured in SOFTWIKI_PROXY_USER_HEADER?"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
