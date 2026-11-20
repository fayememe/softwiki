"""End-to-end check of proxy mode over HTTP (no mocks in the request path).

Two cases must differ:
  1. a trusted proxy peer sending identity headers -> authenticated as that user
  2. an untrusted peer sending the same headers  -> still unauthenticated

Run against a live server or with TestClient; this script uses TestClient.
"""

from __future__ import annotations

import json
import os
import tempfile

os.environ.setdefault("SOFTWIKI_ALLOW_MOCK_EMBEDDINGS", "1")
os.environ.setdefault("SOFTWIKI_DISABLE_LIGHTRAG", "1")
os.environ.setdefault("SOFTWIKI_ENABLE_WEB_SEARCH", "0")

ws = tempfile.mkdtemp(prefix="softwiki-proxy-e2e-")
os.environ["WORKSPACES_ROOT"] = ws
os.makedirs(os.path.join(ws, "kb", ".softwiki"), exist_ok=True)
os.environ["WORKSPACE_DIR"] = os.path.join(ws, "kb")

os.environ["SOFTWIKI_AUTH_MODE"] = "proxy"
os.environ["SOFTWIKI_TRUSTED_PROXIES"] = "testclient"
os.environ["SOFTWIKI_PROXY_USER_HEADER"] = "X-Auth-Request-User"
os.environ["SOFTWIKI_PROXY_GROUPS_HEADER"] = "X-Auth-Request-Groups"

from fastapi.testclient import TestClient  # noqa: E402

from softwiki.api.server import app  # noqa: E402
from softwiki.identity.users import UserStore  # noqa: E402


def main() -> int:
    # Seed the mapping so the proxy identity resolves to a role.
    store = UserStore()
    store.save_mapping({"staff": ["wiki-work"]})

    client = TestClient(app)

    ok = client.get(
        "/api/auth/me",
        headers={
            "X-Auth-Request-User": "alice",
            "X-Auth-Request-Groups": "staff",
        },
    )
    anonymous = client.get(
        "/api/auth/me",
        headers={
            "X-Auth-Request-User": "alice",
            "X-Auth-Request-Groups": "staff",
        },
        # TestClient always reports 127.0.0.1/"testclient"; patching the peer is
        # done by pointing the trusted list at a range that excludes it.
    )

    print("trusted peer:", json.dumps(ok.json(), ensure_ascii=False))
    print("same headers, untrusted peer: simulated below")

    # Simulate an untrusted peer by removing it from the trusted list.
    os.environ["SOFTWIKI_TRUSTED_PROXIES"] = "203.0.113.0/24"
    anonymous = client.get(
        "/api/auth/me",
        headers={"X-Auth-Request-User": "alice", "X-Auth-Request-Groups": "staff"},
    )
    print("untrusted peer:", json.dumps(anonymous.json(), ensure_ascii=False))

    trusted_ok = ok.json().get("authenticated") is True
    forged_rejected = anonymous.json().get("authenticated") is False
    print(f"\ntrusted authenticated={trusted_ok} forged rejected={forged_rejected}")
    return 0 if (trusted_ok and forged_rejected) else 1


if __name__ == "__main__":
    raise SystemExit(main())
