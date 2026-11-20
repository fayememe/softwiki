"""ASGI middleware enforcing softwiki.netacl for the MCP apps."""

from __future__ import annotations

from softwiki import netacl


def _peer(scope) -> str | None:
    client = scope.get("client")
    if not client:
        return None
    return client[0]


class NetworkAllowlistMiddleware:
    """Refuse peers outside SOFTWIKI_ALLOWED_CIDRS.

    Placed outermost so a blocked peer never reaches the tool layer or the
    role-header parsing (a forged role header from a blocked IP is irrelevant).
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        allowed, reason = netacl.check(_peer(scope))
        if not allowed:
            body = (
                '{"jsonrpc":"2.0","id":null,"error":'
                f'{{"code":-32000,"message":"Forbidden: {reason}"}}}}'
            ).encode()
            headers = [(b"content-type", b"application/json")]
            await send({
                "type": "http.response.start",
                "status": 403,
                "headers": headers + [(b"content-length", str(len(body)).encode())],
            })
            await send({"type": "http.response.body", "body": body})
            return

        await self.app(scope, receive, send)
