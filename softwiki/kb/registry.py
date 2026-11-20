"""Knowledge base registry — inspect every kb in the workspaces root.

Design goals (see docs/02-design/multi-kb.md):

- Zero database access. `kb_list` is called by agents *before* they know which kb
  to query; opening every database here would defeat the purpose.
- Three-level description fallback so that every kb can always be described:
    1. config/meta.yaml
    2. scope.md first paragraph
    3. config/topics.yaml groups
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import yaml


@dataclass
class TopicGroup:
    """One topic group as rendered by kb_list."""

    name: str
    topics: List[str] = field(default_factory=list)


@dataclass
class KbInfo:
    """Everything kb_list / kb_describe know about one workspace, without a DB."""

    name: str
    path: str
    description: str = ""
    description_source: str = ""
    groups: List[TopicGroup] = field(default_factory=list)
    language: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    has_index: bool = False
    modules: List[str] = field(default_factory=list)
    # Where this kb's own WebUI is served, when it runs as a separate stack
    # (e.g. "http://host:6109"). Absent means "not navigable from the UI".
    web_url: Optional[str] = None

    @property
    def topic_count(self) -> int:
        return sum(len(g.topics) for g in self.groups)


def _read_yaml(path: str) -> dict:
    """Read a YAML file, returning {} when missing or malformed."""
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as exc:  # noqa: BLE001 - malformed config must not break listing
        print(f"[kb] ignoring unreadable {path}: {exc}", flush=True)
        return {}
    return data if isinstance(data, dict) else {}


def _load_topics(kb_path: str) -> Dict[str, dict]:
    """Return the topic mapping from config/topics.yaml."""
    data = _read_yaml(os.path.join(kb_path, "config", "topics.yaml"))
    if not data:
        return {}
    topics = data.get("topics", data)
    return topics if isinstance(topics, dict) else {}


def _load_meta(kb_path: str) -> dict:
    return _read_yaml(os.path.join(kb_path, "config", "meta.yaml"))


def _first_paragraph(markdown_path: str) -> str:
    """Return the first meaningful paragraph of a markdown file.

    Skips a top-level heading and collects following non-empty lines, joining
    bullet lists into a single sentence. Returns "" when nothing usable exists.
    """
    if not os.path.isfile(markdown_path):
        return ""
    try:
        with open(markdown_path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as exc:
        print(f"[kb] ignoring unreadable {markdown_path}: {exc}", flush=True)
        return ""

    paragraph: List[str] = []
    for raw in lines:
        line = raw.strip()
        if line.startswith("#"):
            # A heading after content ends the paragraph; before content it ends
            # the current empty section and we keep looking.
            if paragraph:
                break
            continue
        if not line:
            if paragraph:
                break
            continue
        # Strip list markers so bullets read as prose.
        if line.startswith(("- ", "* ", "+ ")):
            line = line[2:].strip()
        line = line.replace("**", "")
        paragraph.append(line.rstrip(":;,"))
    return " ".join(paragraph).strip()


def _default_description(kb_path: str, topics: Dict[str, dict]) -> str:
    """Build a fallback description from topic groups, or from loose content."""
    groups = []
    for info in topics.values():
        group = str(info.get("group") or "").strip()
        if group and group not in groups:
            groups.append(group)
    if groups:
        return "Topics: " + ", ".join(groups[:6])

    # No topics and no metadata: say something useful about the kb instead of
    # leaving it blank, so an agent can still tell it apart from other kbs.
    raw_dir = os.path.join(kb_path, "raw")
    file_count = 0
    for _root, _dirs, files in os.walk(raw_dir):
        file_count += len(files)
    if file_count:
        return f"Untitled knowledge base with {file_count} raw file(s), no topics configured"
    return "Empty knowledge base (no topics, no raw files)"


def _resolve_description(kb_path: str, meta: dict, topics: Dict[str, dict]) -> Tuple[str, str]:
    """Apply the three-level fallback; return (description, source)."""
    meta_desc = str(meta.get("description") or "").strip()
    if meta_desc:
        return meta_desc, "meta.yaml"

    scope_desc = _first_paragraph(os.path.join(kb_path, "scope.md"))
    if scope_desc:
        # Keep it to a single readable line.
        scope_desc = " ".join(scope_desc.split())
        if len(scope_desc) > 200:
            scope_desc = scope_desc[:197].rstrip() + "..."
        return scope_desc, "scope.md"

    return _default_description(kb_path, topics), "inferred"


def _build_groups(topics: Dict[str, dict]) -> List[TopicGroup]:
    ordered: Dict[str, TopicGroup] = {}
    for key, info in topics.items():
        info = info if isinstance(info, dict) else {}
        group = str(info.get("group") or "Other").strip() or "Other"
        name = str(info.get("name") or key).strip()
        ordered.setdefault(group, TopicGroup(name=group)).topics.append(name)
    return list(ordered.values())


def _load_modules(kb_path: str) -> List[str]:
    path = os.path.join(kb_path, ".softwiki", "modules.json")
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:  # noqa: BLE001
        print(f"[kb] ignoring unreadable {path}: {exc}", flush=True)
        return []
    if isinstance(data, dict):
        data = data.get("enabled", data.get("modules", []))
    return [str(m) for m in data] if isinstance(data, list) else []


def load_kb(kb_path: str) -> KbInfo:
    """Inspect one workspace directory. Never touches the database."""
    name = os.path.basename(os.path.abspath(kb_path))
    meta = _load_meta(kb_path)
    topics = _load_topics(kb_path)
    description, source = _resolve_description(kb_path, meta, topics)

    # A meta.yaml whose name disagrees with the directory is a mistake worth
    # surfacing, but the directory name always wins (it is what users pass as kb).
    declared = str(meta.get("name") or "").strip()
    if declared and declared != name:
        print(
            f"[kb] {kb_path}: meta.yaml name '{declared}' != directory '{name}'; using directory",
            flush=True,
        )

    tags = meta.get("tags") or []
    if not isinstance(tags, list):
        tags = [str(tags)]

    index_dir = os.path.join(kb_path, ".softwiki", "index")
    has_index = os.path.isfile(os.path.join(index_dir, "vector_index.npz")) or os.path.isfile(
        os.path.join(index_dir, "bm25_index.pkl")
    )

    return KbInfo(
        name=name,
        path=os.path.abspath(kb_path),
        description=description,
        description_source=source,
        groups=_build_groups(topics),
        language=(str(meta["language"]).strip() if meta.get("language") else None),
        tags=[str(t) for t in tags],
        has_index=has_index,
        modules=_load_modules(kb_path),
        web_url=(str(meta["web_url"]).strip() if meta.get("web_url") else None),
    )


def list_kb_infos(root: str) -> List[KbInfo]:
    """Inspect every initialised workspace under root, sorted by name."""
    if not os.path.isdir(root):
        return []
    infos: List[KbInfo] = []
    for name in sorted(os.listdir(root)):
        kb_path = os.path.join(root, name)
        if not os.path.isdir(kb_path):
            continue
        if not os.path.isdir(os.path.join(kb_path, ".softwiki")):
            continue
        infos.append(load_kb(kb_path))
    return infos


def resolve_kb_path(root: str, kb: str) -> Optional[str]:
    """Resolve a kb name to its directory, or None when it is not a valid kb."""
    if not kb:
        return None
    candidate = os.path.abspath(os.path.join(root, kb))
    # Reject traversal: the resolved path must be a direct child of root.
    if os.path.dirname(candidate) != os.path.abspath(root):
        return None
    if not os.path.isdir(candidate):
        return None
    if not os.path.isdir(os.path.join(candidate, ".softwiki")):
        return None
    return candidate


def render_kb_list(infos: List[KbInfo], active: Optional[str] = None) -> str:
    """Render kb_list output for agents."""
    if not infos:
        return "No knowledge bases found."

    lines = [f"Knowledge bases ({len(infos)}):", ""]
    for info in infos:
        marker = "   [active]" if active and info.name == active else ""
        lines.append(f"## {info.name}{marker}")
        if info.description:
            lines.append(f"   Description: {info.description}")
        if info.language:
            lines.append(f"   Language: {info.language}")
        if info.groups:
            lines.append("   Topics:")
            for group in info.groups:
                lines.append(f"     {group.name:<14} : {', '.join(group.topics)}")
        else:
            lines.append("   Topics: (none configured)")
        lines.append("")
    lines.append("Pass the kb name to ask() or search(), e.g. ask(query, kb=\"lsl-kb\").")
    return "\n".join(lines).rstrip()


def render_kb_describe(info: KbInfo, topics_raw: Dict[str, dict]) -> str:
    """Render one kb in full detail, including synonyms and diagnostics."""
    lines = [f"# {info.name}", "", f"Path: {info.path}"]
    lines.append(
        f"Description ({info.description_source}): {info.description or '(none)'}"
    )
    if info.language:
        lines.append(f"Language: {info.language}")
    if info.tags:
        lines.append(f"Tags: {', '.join(info.tags)}")
    if info.modules:
        lines.append(f"Modules: {', '.join(info.modules)}")
    lines.append(f"Search index: {'present' if info.has_index else 'missing'}")
    lines.append("")
    if topics_raw:
        lines.append("## Topics")
        for key, raw in topics_raw.items():
            raw = raw if isinstance(raw, dict) else {}
            group = raw.get("group") or "Other"
            name = raw.get("name") or key
            lines.append(f"- [{group}] {name} ({key})")
            if raw.get("description"):
                lines.append(f"    {raw['description']}")
            synonyms = raw.get("synonyms") or []
            if synonyms:
                lines.append(f"    synonyms: {', '.join(str(s) for s in synonyms)}")
    else:
        lines.append("No topics configured.")
    return "\n".join(lines).rstrip()


def get_kb_topics(kb_path: str) -> Dict[str, dict]:
    """Public accessor used by kb_describe."""
    return _load_topics(kb_path)
