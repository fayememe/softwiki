"""Request-scoped knowledge base selection for MCP and API entry points.

Design (docs/02-design/multi-kb.md §2.1):

- The kb is resolved per call and published through a ContextVar, which the
  existing `get_workspace_dir()` already honours.
- `set_workspace_dir()` (which writes `os.environ`) is never called from a
  request path: that would leak one caller's kb into every other caller.
- MCP tools are plain synchronous functions and FastMCP awaits them in the
  caller's coroutine, so a ContextVar set by the ASGI middleware survives into
  the tool call.
"""

from __future__ import annotations

import contextvars
import os
from typing import Optional

from softwiki.config import get_workspaces_root, set_request_workspace

_current_kb: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_kb", default=None
)


class KbResolutionError(LookupError):
    """Raised when a kb name cannot be resolved to an initialised workspace."""


def resolve_kb_dir(kb: str, root: Optional[str] = None) -> Optional[str]:
    """Resolve a kb name to its directory, rejecting traversal and unknown kbs.

    A valid kb is a direct child of the workspaces root containing `.softwiki/`.
    """
    if not kb:
        return None
    base = os.path.abspath(root or get_workspaces_root())
    candidate = os.path.abspath(os.path.join(base, kb))
    if os.path.dirname(candidate) != base:
        return None
    if not os.path.isdir(os.path.join(candidate, ".softwiki")):
        return None
    return candidate


def current_kb_name() -> Optional[str]:
    """Name of the kb in effect for this execution context, if any."""
    return _current_kb.get()


def _apply(kb_name: Optional[str]) -> None:
    _current_kb.set(kb_name)
    set_request_workspace(resolve_kb_dir(kb_name) if kb_name else None)


def default_kb_name() -> Optional[str]:
    """The kb a *user* means when a tool omits `kb`.

    Request paths already carry it (middleware enters the user's active kb), but
    the MCP server runs in its own process: its tools defaulted to the instance
    workspace, so the assistant kept querying armkb after the UI switched to
    another kb. In `off` mode there is exactly one user, whose `active_kb` is the
    same preference the UI writes.
    """
    current = current_kb_name()
    if current:
        return current
    try:
        from softwiki.identity.superuser import auth_mode

        if auth_mode() != "off":
            return None
        from softwiki.identity.users import UserStore

        name = getattr(UserStore().ensure_superuser_row(), "active_kb", None)
        if name and resolve_kb_dir(name):
            return name
    except Exception:  # noqa: BLE001 - a broken users.yaml must not break tools
        return None
    return None


def enter_kb(kb: Optional[str]) -> Optional[str]:
    """Scope this execution context to `kb`; returns the previous kb name.

    `kb=None` is a no-op so the ambient (default) workspace stays in effect.
    Always pair with `restore_kb(previous)` in a finally block.
    """
    if not kb:
        return _current_kb.get()

    if resolve_kb_dir(kb) is None:
        raise KbResolutionError(
            f"Knowledge base '{kb}' not found. Call kb_list() to see available kb names."
        )
    previous = _current_kb.get()
    _apply(os.path.basename(kb))
    return previous


def restore_kb(previous: Optional[str]) -> None:
    """Restore the kb that was in effect before `enter_kb`."""
    _apply(previous)


class KbHeaderMiddleware:
    """ASGI middleware: select the kb from an `X-SoftWiki-KB` header.

    Agents may pin one kb per connection; individual tool calls can still
    override it through their `kb` argument.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }
        requested = (headers.get("x-softwiki-kb") or "").strip()
        if not requested:
            # No explicit pin: follow the same preference the UI switch writes,
            # otherwise every kb-scoped tool (status, list_*, rebuild) answered
            # for the instance default instead of the kb on screen.
            requested = default_kb_name() or ""
        if not requested:
            await self.app(scope, receive, send)
            return

        try:
            previous = enter_kb(requested)
        except KbResolutionError as exc:
            print(f"[kb] ignoring X-SoftWiki-KB: {exc}", flush=True)
            await self.app(scope, receive, send)
            return

        try:
            await self.app(scope, receive, send)
        finally:
            restore_kb(previous)
