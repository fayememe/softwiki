"""Tests for multi-kb support (docs/02-design/multi-kb.md)."""

import os
import shutil

import pytest

from softwiki.config import get_workspace_dir, set_request_workspace
from softwiki.kb.context import (
    KbResolutionError,
    enter_kb,
    resolve_kb_dir,
    restore_kb,
)
from softwiki.kb.registry import (
    get_kb_topics,
    list_kb_infos,
    load_kb,
    render_kb_describe,
    render_kb_list,
)


def _make_kb(root, name, *, meta=None, scope=None, topics=None, index=False):
    """Create a minimal initialised workspace under root."""
    path = os.path.join(root, name)
    os.makedirs(os.path.join(path, ".softwiki", "index"), exist_ok=True)
    os.makedirs(os.path.join(path, "config"), exist_ok=True)

    if meta is not None:
        import yaml

        with open(os.path.join(path, "config", "meta.yaml"), "w", encoding="utf-8") as f:
            yaml.safe_dump(meta, f, allow_unicode=True)

    if scope is not None:
        with open(os.path.join(path, "scope.md"), "w", encoding="utf-8") as f:
            f.write(scope)

    if topics is not None:
        import yaml

        with open(os.path.join(path, "config", "topics.yaml"), "w", encoding="utf-8") as f:
            yaml.safe_dump({"topics": topics}, f, allow_unicode=True)

    if index:
        open(os.path.join(path, ".softwiki", "index", "bm25_index.pkl"), "wb").close()

    return path


@pytest.fixture()
def kbs_root(tmp_path, monkeypatch):
    """Two kbs plus a bare directory, rooted at tmp_path."""
    root = str(tmp_path / "workspaces")
    os.makedirs(root, exist_ok=True)
    _make_kb(
        root,
        "alpha-kb",
        meta={"name": "alpha-kb", "description": "Alpha topics", "tags": ["a"]},
        topics={"t1": {"name": "Topic One", "group": "Group A"}},
        index=True,
    )
    _make_kb(
        root,
        "beta-kb",
        scope="# Beta\n\nBeta covers the second subject.\n",
        topics={"t2": {"name": "Topic Two", "group": "Group B"}},
    )
    # A directory without .softwiki is not a kb and must be ignored.
    os.makedirs(os.path.join(root, "not-a-kb"), exist_ok=True)
    monkeypatch.setenv("WORKSPACES_ROOT", root)
    return root


def test_list_kb_infos_only_initialised(kbs_root):
    names = [info.name for info in list_kb_infos(kbs_root)]
    assert names == ["alpha-kb", "beta-kb"]


def test_description_prefers_meta_yaml(kbs_root):
    info = load_kb(os.path.join(kbs_root, "alpha-kb"))
    assert info.description == "Alpha topics"
    assert info.description_source == "meta.yaml"
    assert info.language is None
    assert info.tags == ["a"]
    assert info.has_index is True


def test_description_falls_back_to_scope(kbs_root):
    info = load_kb(os.path.join(kbs_root, "beta-kb"))
    assert info.description == "Beta covers the second subject."
    assert info.description_source == "scope.md"


def test_description_falls_back_to_topics(tmp_path):
    root = str(tmp_path / "ws")
    os.makedirs(root)
    _make_kb(root, "gamma-kb", topics={"t": {"name": "T", "group": "Gamma Group"}})
    info = load_kb(os.path.join(root, "gamma-kb"))
    assert info.description_source == "inferred"
    assert "Gamma Group" in info.description


def test_description_never_empty(tmp_path):
    root = str(tmp_path / "ws")
    os.makedirs(root)
    _make_kb(root, "empty-kb")
    info = load_kb(os.path.join(root, "empty-kb"))
    assert info.description  # always something an agent can read


def test_render_kb_list_mentions_topics_and_active(kbs_root):
    infos = list_kb_infos(kbs_root)
    text = render_kb_list(infos, active="alpha-kb")
    assert "alpha-kb" in text and "beta-kb" in text
    assert "[active]" in text
    assert "Group A" in text and "Topic One" in text
    assert "kb=" in text  # tells the agent how to use the names


def test_render_kb_describe_includes_synonyms(tmp_path):
    root = str(tmp_path / "ws")
    os.makedirs(root)
    _make_kb(
        root,
        "delta-kb",
        topics={
            "d1": {
                "name": "Delta Topic",
                "group": "G",
                "description": "desc here",
                "synonyms": ["D", "delta"],
            }
        },
    )
    path = os.path.join(root, "delta-kb")
    text = render_kb_describe(load_kb(path), get_kb_topics(path))
    assert "Delta Topic" in text
    assert "synonyms: D, delta" in text
    assert "desc here" in text


def test_resolve_kb_dir_rejects_traversal_and_unknown(kbs_root):
    assert resolve_kb_dir("alpha-kb") is not None
    assert resolve_kb_dir("../alpha-kb") is None
    assert resolve_kb_dir("not-a-kb") is None
    assert resolve_kb_dir("missing-kb") is None
    assert resolve_kb_dir("") is None


def test_enter_kb_scopes_workspace_and_restores(kbs_root):
    original = get_workspace_dir()
    previous = enter_kb("alpha-kb")
    try:
        assert get_workspace_dir() == os.path.join(kbs_root, "alpha-kb")

        # Switching again inside the scope must work, and restoring returns to alpha.
        inner = enter_kb("beta-kb")
        assert get_workspace_dir() == os.path.join(kbs_root, "beta-kb")
        restore_kb(inner)
        assert get_workspace_dir() == os.path.join(kbs_root, "alpha-kb")
    finally:
        restore_kb(previous)

    assert get_workspace_dir() == original


def test_enter_kb_none_is_noop(kbs_root):
    original = get_workspace_dir()
    previous = enter_kb(None)
    try:
        assert get_workspace_dir() == original
    finally:
        restore_kb(previous)


def test_enter_kb_unknown_raises_with_hint(kbs_root):
    with pytest.raises(KbResolutionError) as excinfo:
        enter_kb("nope-kb")
    assert "kb_list" in str(excinfo.value)


def test_enter_kb_does_not_touch_process_env(kbs_root, monkeypatch):
    """A request-scoped kb must not leak into os.environ."""
    monkeypatch.setenv("WORKSPACE_DIR", os.path.join(kbs_root, "beta-kb"))
    before = os.environ.get("WORKSPACE_DIR")

    previous = enter_kb("alpha-kb")
    try:
        assert get_workspace_dir() == os.path.join(kbs_root, "alpha-kb")
        assert os.environ.get("WORKSPACE_DIR") == before
    finally:
        restore_kb(previous)


def test_kb_list_does_not_open_database(kbs_root, monkeypatch):
    """kb_list must stay file-only; opening a DB would preload every kb."""
    from softwiki.mcp import server as mcp_server
    from softwiki.source_store import db as db_module

    opened = []

    def _boom(*args, **kwargs):  # pragma: no cover - only runs on failure
        opened.append(True)
        raise AssertionError("kb_list must not create a database session")

    monkeypatch.setattr(db_module, "get_engine", _boom)
    monkeypatch.setattr(mcp_server, "SessionLocal", _boom)

    text = mcp_server.kb_list()
    assert "alpha-kb" in text
    assert opened == []


def test_mcp_ask_rejects_unknown_kb(kbs_root):
    from softwiki.mcp import server as mcp_server

    result = mcp_server.ask("anything", kb="does-not-exist")
    assert "not found" in result
    assert "kb_list" in result


def test_mcp_kb_describe_unknown(kbs_root):
    from softwiki.mcp import server as mcp_server

    result = mcp_server.kb_describe("does-not-exist")
    assert "not found" in result


def test_current_kb_isolation_between_contexts(kbs_root):
    """Two concurrent execution contexts must not see each other's kb."""
    import contextvars

    seen = {}

    def worker(name):
        previous = enter_kb(name)
        try:
            seen[name] = os.path.basename(get_workspace_dir())
        finally:
            restore_kb(previous)

    ctx_a = contextvars.copy_context()
    ctx_b = contextvars.copy_context()
    ctx_a.run(worker, "alpha-kb")
    ctx_b.run(worker, "beta-kb")

    assert seen == {"alpha-kb": "alpha-kb", "beta-kb": "beta-kb"}
