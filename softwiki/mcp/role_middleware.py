"""ASGI middleware: role header -> contextvar for MCP tool calls."""
from __future__ import annotations

from softwiki.permissions import normalize_role, reset_role, set_role


class RoleMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        role = headers.get("x-softwiki-role") or headers.get("x-softwiki-mode")
        token = set_role(normalize_role(role)) if role else None
        try:
            await self.app(scope, receive, send)
        finally:
            if token is not None:
                reset_role(token)
