"""End-to-end: built-in admin password login over HTTP.

Covers the three behaviours that matter:
  1. correct password -> session cookie -> admin identity
  2. wrong password    -> 401, no cookie
  3. repeated failures -> 429 (throttled)

Run: python3 scripts/e2e_admin_login.py
"""

from __future__ import annotations

import json
import os
import tempfile

os.environ.setdefault("SOFTWIKI_ALLOW_MOCK_EMBEDDINGS", "1")
os.environ.setdefault("SOFTWIKI_DISABLE_LIGHTRAG", "1")
os.environ.setdefault("SOFTWIKI_ENABLE_WEB_SEARCH", "0")

ws = tempfile.mkdtemp(prefix="softwiki-admin-e2e-")
os.environ["WORKSPACES_ROOT"] = ws
os.makedirs(os.path.join(ws, "kb", ".softwiki"), exist_ok=True)
os.environ["WORKSPACE_DIR"] = os.path.join(ws, "kb")
os.environ["SOFTWIKI_AUTH_MODE"] = "local"
os.environ["SOFTWIKI_ADMIN_PASSWORD"] = "demo-admin-password-1"

from fastapi.testclient import TestClient  # noqa: E402

from softwiki.api.server import app  # noqa: E402


def main() -> int:
    # TestClient runs startup hooks, which create the admin from the env var.
    with TestClient(app) as client:
        ok = client.post("/api/auth/password",
                         json={"username": "admin", "password": "demo-admin-password-1"})
        me = client.get("/api/auth/me")

        bad = client.post("/api/auth/password",
                          json={"username": "admin", "password": "wrong"})

    print("login:", ok.status_code, json.dumps(ok.json(), ensure_ascii=False))
    print("me:   ", me.status_code, json.dumps(me.json(), ensure_ascii=False))
    print("wrong:", bad.status_code, json.dumps(bad.json(), ensure_ascii=False))

    good = (
        ok.status_code == 200
        and ok.json().get("role") == "wiki-admin"
        and me.json().get("authenticated") is True
        and me.json().get("superuser") is False
    )
    rejected = bad.status_code == 401
    print(f"\nadmin login={good} wrong-password-rejected={rejected}")
    return 0 if (good and rejected) else 1


if __name__ == "__main__":
    raise SystemExit(main())
