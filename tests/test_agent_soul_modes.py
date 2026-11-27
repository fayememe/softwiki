"""The browser agent's soul must match the project, not always be 'research'.

Work / Manage / Admin chats used the read-only research soul, so every request
was answered through softwiki_ask instead of being carried out.
"""

import os

from softwiki.cli.shell import _agent_permissions, _get_agent_soul

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WS = "/tmp/softwiki-agent-soul-test"


def test_manage_project_gets_the_management_soul():
    soul = _get_agent_soul(WS, ROOT, web=True, mode="wiki-manage")
    assert "知识库管理员" in soul
    assert "Research Agent" not in soul


def test_research_mode_keeps_the_research_soul():
    soul = _get_agent_soul(WS, ROOT, web=True, mode="wiki-research")
    assert "Research Agent" in soul


def test_study_mode_keeps_the_research_soul():
    soul = _get_agent_soul(WS, ROOT, web=True, mode="wiki-study")
    assert "Research Agent" in soul


def test_admin_shell_keeps_the_management_soul():
    soul = _get_agent_soul(WS, ROOT, web=False, mode="wiki-admin")
    assert "知识库管理员" in soul


def test_management_tools_are_gated_by_mode():
    manage = _agent_permissions("wiki-manage")
    assert "softwiki_wiki_subject_build" not in manage
    assert "softwiki_resume_extraction" not in manage

    work = _agent_permissions("wiki-work")
    assert work["softwiki_wiki_subject_build"] == "deny"
    assert work["softwiki_resume_extraction"] == "deny"

    research = _agent_permissions("wiki-research")
    assert research["softwiki_wiki_subject_build"] == "deny"
    assert research["softwiki_resume_extraction"] == "deny"
