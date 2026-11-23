"""Regression: the auth gate must not depend on middleware order.

`auth_middleware` is registered after `role_middleware`, so it runs *first*.
Before the fix it read `request.state.identity` before anything had resolved it
and answered 401 for every non-exempt path in proxy/local/oidc mode. Only
`/api/auth/me` (exempt) looked fine, which hid the bug.
"""

from __future__ import annotations

import os
import tempfile

os.environ.setdefault("SOFTWIKI_ALLOW_MOCK_EMBEDDINGS", "1")
os.environ.setdefault("SOFTWIKI_DISABLE_LIGHTRAG", "1")
os.environ.setdefault("SOFTWIKI_ENABLE_WEB_SEARCH", "0")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    ws = str(tmp_path)
    monkeypatch.setenv("WORKSPACES_ROOT", ws)
    os.makedirs(os.path.join(ws, "kb", ".softwiki"), exist_ok=True)
    monkeypatch.setenv("WORKSPACE_DIR", os.path.join(ws, "kb"))
    monkeypatch.setenv("SOFTWIKI_AUTH_MODE", "proxy")
    monkeypatch.setenv("SOFTWIKI_TRUSTED_PROXIES", "testclient")
    monkeypatch.setenv("SOFTWIKI_PROXY_USER_HEADER", "X-Auth-Request-User")
    monkeypatch.setenv("SOFTWIKI_PROXY_GROUPS_HEADER", "X-Auth-Request-Groups")

    from softwiki.api import server

    with TestClient(server.app) as c:
        yield c


def test_authenticated_request_reaches_a_protected_path(client):
    """A resolved identity must satisfy the gate on a non-exempt route."""
    r = client.get("/api/documents", headers={"X-Auth-Request-User": "alice"})
    assert r.status_code != 401, "the gate ran before identity resolution"


def test_anonymous_request_still_rejected_on_protected_path(client):
    r = client.get("/api/documents", headers={"X-Auth-Request-User": ""})
    assert r.status_code == 401
