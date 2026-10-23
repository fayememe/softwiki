from softwiki.config import get_workspaces_root, list_workspaces


def test_workspaces_root_defaults_to_workspace_dir_parent(tmp_path, monkeypatch):
    root = tmp_path / "workspaces"
    for name in ("alpha", "beta"):
        (root / name / ".softwiki").mkdir(parents=True)
    monkeypatch.setenv("WORKSPACE_DIR", str(root / "alpha"))
    monkeypatch.delenv("WORKSPACES_ROOT", raising=False)
    assert get_workspaces_root() == str(root)
    assert list_workspaces() == ["alpha", "beta"]


def test_workspaces_root_env_override(tmp_path, monkeypatch):
    root = tmp_path / "custom"
    (root / "gamma" / ".softwiki").mkdir(parents=True)
    monkeypatch.setenv("WORKSPACES_ROOT", str(root))
    assert get_workspaces_root() == str(root)
    assert list_workspaces() == ["gamma"]
