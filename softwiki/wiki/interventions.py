"""User prompt interventions for wiki generation.

An intervention is deliberately *not* a fixed profile. It is free text that can
be empty, one sentence, a section rule, or a full template. The generator
receives the composed text as an additional highest-priority instruction.
"""
from __future__ import annotations

import fnmatch
import hashlib
import os
import re
from datetime import datetime
from typing import Any, Optional

import yaml

from softwiki.config import get_config_path, get_export_dir


def _store_path() -> str:
    return get_config_path("wiki_interventions.yaml")


def _read_store() -> dict:
    path = _store_path()
    if not os.path.exists(path):
        return {"interventions": []}
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            return {"interventions": []}
        data.setdefault("interventions", [])
        return data
    except Exception:
        return {"interventions": []}


def _write_store(data: dict) -> None:
    path = _store_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
    os.replace(tmp, path)


def _scope_slug(scope: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", scope).strip("-").lower() or "global"


def list_interventions() -> list[dict]:
    items = list(_read_store().get("interventions", []))
    return sorted(
        items,
        key=lambda x: (str(x.get("scope", "")), int(x.get("priority", 100)),
                       str(x.get("updated_at", ""))),
    )


def save_intervention(scope: str, text: str, intervention_id: Optional[str] = None,
                      enabled: bool = True, priority: int = 100) -> dict:
    scope = (scope or "global").strip()
    if not (scope == "global" or scope.startswith("group:") or scope.startswith("topic:")):
        raise ValueError("scope must be global, group:<name>, or topic:<id>")
    if scope in ("group:", "topic:"):
        raise ValueError("group/topic scope needs a name")
    if not isinstance(priority, int):
        priority = int(priority)

    data = _read_store()
    items = data.setdefault("interventions", [])
    text = (text or "").strip()
    iid = intervention_id or f"{_scope_slug(scope)}-{hashlib.md5(text.encode('utf-8')).hexdigest()[:8]}"
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    existing = next((x for x in items if x.get("id") == iid), None)
    if existing:
        existing.update({
            "scope": scope,
            "text": text,
            "enabled": bool(enabled),
            "priority": priority,
            "version": int(existing.get("version", 1)) + 1,
            "updated_at": now,
        })
        saved = existing
    else:
        saved = {
            "id": iid,
            "scope": scope,
            "text": text,
            "enabled": bool(enabled),
            "priority": priority,
            "version": 1,
            "created_at": now,
            "updated_at": now,
        }
        items.append(saved)
    _write_store(data)
    return saved


def delete_intervention(intervention_id: str) -> bool:
    data = _read_store()
    items = data.get("interventions", [])
    kept = [x for x in items if x.get("id") != intervention_id]
    if len(kept) == len(items):
        return False
    data["interventions"] = kept
    _write_store(data)
    return True


def topic_info(topic: str) -> dict:
    path = get_config_path("topics.yaml")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        topics = data.get("topics", data) if isinstance(data, dict) else {}
        info = topics.get(topic, {}) if isinstance(topics, dict) else {}
        return info if isinstance(info, dict) else {}
    except Exception:
        return {}


def topic_group(topic: str) -> str:
    """The first-level knowledge category (IP 产品 / 协议 / 技术)."""
    info = topic_info(topic)
    return str(info.get("category") or info.get("group") or "Other")


def topic_aliases(topic: str) -> list[str]:
    info = topic_info(topic)
    aliases = info.get("aliases") or []
    return [str(x) for x in aliases if str(x).strip()]


def topic_name(topic: str) -> str:
    info = topic_info(topic)
    return str(info.get("name") or topic.replace("-", " ").title())


def compose_interventions(topic: str, adhoc: str = "",
                          include_saved: bool = True) -> str:
    """Compose optional saved layers and an ad-hoc intervention.

    The output is free-form text. It can be empty, one sentence, or a full
    template. The generator treats it as a highest-priority instruction.
    """
    group = topic_group(topic)
    layers: list[tuple[int, str, str]] = []
    if include_saved:
        for item in list_interventions():
            if not item.get("enabled", True):
                continue
            scope = str(item.get("scope", ""))
            if scope == "global":
                label = "GLOBAL"
            elif scope == f"group:{group}":
                label = f"GROUP: {group}"
            elif scope == f"topic:{topic}":
                label = f"TOPIC: {topic}"
            else:
                continue
            layers.append((int(item.get("priority", 100)), label, str(item.get("text", ""))))
    if (adhoc or "").strip():
        layers.append((1_000_000, "AD-HOC PREVIEW", adhoc.strip()))
    if not layers:
        return ""
    layers.sort(key=lambda x: x[0])
    parts = [
        "The following are USER INTERVENTIONS for this wiki page. They override "
        "the default structure where they conflict. They are instructions, not "
        "source evidence; never treat them as facts.",
    ]
    for _, label, text in layers:
        parts.append(f"[{label}]\n{text}")
    return "\n\n".join(parts)


def preview_dir(run_id: str) -> str:
    path = os.path.join(get_export_dir("wiki/preview"), run_id)
    os.makedirs(path, exist_ok=True)
    return path


def page_topics_for_claim_topic(claim_topic: str) -> list[str]:
    """Map a raw claim topic (e.g. rtc-register-map) to curated page topics.

    A page owns an alias pattern such as ``rtc-*``; this is the reverse lookup
    used for staleness after claim/adjudication changes.
    """
    path = get_config_path("topics.yaml")
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        topics = data.get("topics", data) if isinstance(data, dict) else {}
    except Exception:
        return []
    pages = []
    for page, info in (topics.items() if isinstance(topics, dict) else []):
        if not isinstance(info, dict):
            continue
        if info.get("kind") not in ("page", None):
            continue
        aliases = [str(a) for a in (info.get("aliases") or []) if str(a).strip()]
        if claim_topic == page or any(fnmatch.fnmatch(claim_topic, a) for a in aliases):
            pages.append(page)
    return pages
