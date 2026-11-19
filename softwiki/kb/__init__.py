"""Knowledge base registry — see docs/02-design/multi-kb.md."""

from softwiki.kb.registry import (
    KbInfo,
    TopicGroup,
    get_kb_topics,
    list_kb_infos,
    load_kb,
    render_kb_describe,
    render_kb_list,
    resolve_kb_path,
)

__all__ = [
    "KbInfo",
    "TopicGroup",
    "get_kb_topics",
    "list_kb_infos",
    "load_kb",
    "render_kb_describe",
    "render_kb_list",
    "resolve_kb_path",
]
