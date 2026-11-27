"""MCP requests without an explicit kb must run against the user's active kb.

The assistant is a separate process; only `ask`/`search` used to resolve the
user's active kb, so `status`, `list_documents`, `rebuild_index` etc. reported
(or wrote) the instance default.
"""

import pytest


@pytest.mark.anyio
async def test_middleware_enters_active_kb_without_header(monkeypatch, tmp_path):
    from softwiki.kb import context as kbctx

    (tmp_path / "demo-kb" / ".softwiki").mkdir(parents=True)
    monkeypatch.setenv("WORKSPACES_ROOT", str(tmp_path))
    monkeypatch.setattr(kbctx, "default_kb_name", lambda: "demo-kb")

    seen = {}

    async def app(scope, receive, send):
        seen["kb"] = kbctx.current_kb_name()

    middleware = kbctx.KbHeaderMiddleware(app)
    await middleware({"type": "http", "headers": []}, None, None)

    assert seen["kb"] == "demo-kb"
    # The context must not leak into the next request.
    assert kbctx.current_kb_name() is None


@pytest.fixture
def anyio_backend():
    return "asyncio"
