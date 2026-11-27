"""Agent-profile tool permissions must match the role capability table.

These tests are the guard against "the three assistant tabs only differ in
their prompt": each project must also be denied the tools its role cannot use.
"""
from softwiki.cli.shell import _agent_permissions
from softwiki.permissions import DEFAULT_ROLES, role_rank


BASE_DENIED = {"bash", "edit", "write"}


def test_every_profile_denies_shell_and_file_edits():
    for mode in ("wiki-study", "wiki-work", "wiki-manage", "wiki-admin", "wiki-research"):
        denied = _agent_permissions(mode)
        assert BASE_DENIED <= set(denied), mode


def test_read_only_profiles_cannot_submit_or_write():
    for mode in ("wiki-study", "wiki-research"):
        denied = _agent_permissions(mode)
        assert "softwiki_wiki_propose" in denied
        assert "softwiki_ingest_url" in denied
        assert "softwiki_ingest_file" in denied
        assert "softwiki_rebuild_index" in denied
        assert "softwiki_wiki_build" in denied


def test_work_may_propose_but_not_ingest():
    denied = _agent_permissions("wiki-work")
    assert "softwiki_wiki_propose" not in denied
    assert "softwiki_ingest_url" in denied
    assert "softwiki_ingest_file" in denied
    assert "softwiki_rebuild_index" in denied


def test_manage_may_ingest_but_not_touch_workspace_or_modules():
    denied = _agent_permissions("wiki-manage")
    assert "softwiki_ingest_url" not in denied
    assert "softwiki_ingest_file" not in denied
    assert "softwiki_rebuild_index" not in denied
    assert "softwiki_wiki_build" not in denied
    assert "softwiki_workspace_set" in denied
    assert "softwiki_modules_set" in denied


def test_admin_keeps_every_kb_tool():
    denied = _agent_permissions("wiki-admin")
    assert set(denied) == BASE_DENIED


def test_permission_table_follows_capability_ranking():
    """A higher role must never be denied a tool a lower role may use."""
    order = ["wiki-study", "wiki-work", "wiki-manage", "wiki-admin"]
    assert role_rank(order[0]) < role_rank(order[-1])
    tools = {
        "softwiki_ingest_url",
        "softwiki_ingest_file",
        "softwiki_rebuild_index",
        "softwiki_wiki_build",
        "softwiki_wiki_propose",
    }
    for lower, higher in zip(order, order[1:]):
        low_denied = set(_agent_permissions(lower)) & tools
        high_denied = set(_agent_permissions(higher)) & tools
        assert high_denied <= low_denied, (lower, higher)


def test_capability_table_still_gates_submit_for_study():
    assert "wiki.submit" not in DEFAULT_ROLES["wiki-study"]
    assert "wiki.submit" in DEFAULT_ROLES["wiki-work"]
