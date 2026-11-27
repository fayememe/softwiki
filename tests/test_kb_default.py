"""MCP tools without an explicit `kb` must follow the user's active kb.

The assistant runs as a separate process (opencode + MCP), so it never saw the
UI's kb switch: every question was answered from the instance's default
workspace (armkb), even when the UI was showing another kb.
"""


def _make_kb(root, name):
    (root / name / ".softwiki").mkdir(parents=True, exist_ok=True)
    (root / name / "config").mkdir(exist_ok=True)


def test_default_kb_follows_the_users_active_kb(tmp_path, monkeypatch):
    root = tmp_path / "ws"
    _make_kb(root, "kb-a")
    _make_kb(root, "kb-b")
    monkeypatch.setenv("WORKSPACES_ROOT", str(root))
    monkeypatch.setenv("WORKSPACE_DIR", str(root / "kb-a"))
    monkeypatch.delenv("SOFTWIKI_AUTH_MODE", raising=False)
    monkeypatch.delenv("SOFTWIKI_AUTH_ENABLED", raising=False)

    from softwiki.identity.users import UserStore

    store = UserStore()
    user = store.ensure_superuser_row()
    store.update(user.issuer, user.subject, active_kb="kb-b")

    from softwiki.kb.context import default_kb_name

    assert default_kb_name() == "kb-b"


def test_default_kb_is_none_when_auth_is_on(tmp_path, monkeypatch):
    root = tmp_path / "ws"
    _make_kb(root, "kb-a")
    monkeypatch.setenv("WORKSPACES_ROOT", str(root))
    monkeypatch.setenv("WORKSPACE_DIR", str(root / "kb-a"))
    monkeypatch.setenv("SOFTWIKI_AUTH_MODE", "proxy")

    from softwiki.identity.users import UserStore

    store = UserStore()
    user = store.ensure_superuser_row()
    store.update(user.issuer, user.subject, active_kb="kb-a")

    from softwiki.kb.context import default_kb_name

    assert default_kb_name() is None
