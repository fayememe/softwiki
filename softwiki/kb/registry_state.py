"""Knowledge base registry state: which kbs softwiki acknowledges.

A kb used to exist simply by having a directory. That is enough for a single
operator but not for a platform:

* an *unregistered* kb must disappear from softwiki (agents, web, api) while its
  data stays on disk, so it can be re-registered later — the "unhook, not
  delete" rule from docs/02-design/auth-oidc.md §6;
* a *created* kb needs a record of who made it, from which template, and when;
* per-user `kb_scope` needs a list of kb names that does not depend on scanning
  directories under the workspaces root.

The state lives in ``<workspaces root>/config/kbs.yaml``: YAML next to the other
workspace configuration, diffable, no migration to run.

Backwards compatibility matters: an existing deployment has directories and no
registry file. Those kbs are treated as registered on first read, so nothing
disappears when this module is introduced.
"""
from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, List, Optional

import yaml

from softwiki.config import get_workspaces_root

logger = logging.getLogger(__name__)

REGISTRY_FILE = "kbs.yaml"
TEMPLATES_DIR = "kb-templates"

#: Templates shipped with softwiki. ``generic`` is the safe default.
BUILTIN_TEMPLATES = ("generic", "research-report", "course-qa")

STATUS_REGISTERED = "registered"
STATUS_UNREGISTERED = "unregistered"


@dataclass
class KbRecord:
    name: str
    status: str = STATUS_REGISTERED
    description: str = ""
    template: str = "generic"
    language: Optional[str] = None
    created_at: Optional[str] = None
    created_by: Optional[str] = None
    unregistered_at: Optional[str] = None
    unregistered_by: Optional[str] = None
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "description": self.description,
            "template": self.template,
            "language": self.language,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "unregistered_at": self.unregistered_at,
            "unregistered_by": self.unregistered_by,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, name: str, data: dict) -> "KbRecord":
        return cls(
            name=name,
            status=str(data.get("status") or STATUS_REGISTERED),
            description=str(data.get("description") or ""),
            template=str(data.get("template") or "generic"),
            language=data.get("language"),
            created_at=data.get("created_at"),
            created_by=data.get("created_by"),
            unregistered_at=data.get("unregistered_at"),
            unregistered_by=data.get("unregistered_by"),
            notes=str(data.get("notes") or ""),
        )

    @property
    def registered(self) -> bool:
        return self.status == STATUS_REGISTERED


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _is_kb_dir(path: str) -> bool:
    return os.path.isdir(os.path.join(path, ".softwiki"))


class KbRegistry:
    """Read/update the kb registry."""

    def __init__(self, root: Optional[str] = None):
        self.root = root or get_workspaces_root()

    # -- storage ---------------------------------------------------------

    @property
    def path(self) -> str:
        return os.path.join(self.root, "config", REGISTRY_FILE)

    def _load_raw(self) -> dict:
        path = self.path
        if not os.path.isfile(path):
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception as exc:  # noqa: BLE001 - a broken registry must not hide every kb
            logger.error("ignoring unreadable %s: %s", path, exc)
            return {}
        raw = data.get("kbs") if isinstance(data, dict) else {}
        return raw if isinstance(raw, dict) else {}

    def _save_raw(self, raw: dict) -> None:
        path = self.path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            yaml.safe_dump({"kbs": raw}, f, allow_unicode=True, sort_keys=True)
        os.replace(tmp, path)

    # -- queries ---------------------------------------------------------

    def known_names(self) -> List[str]:
        """Every kb the registry knows about, registered or not."""
        return sorted(self._load_raw())

    def all_kbs(self) -> List[str]:
        """Every kb that currently exists on disk (registered or not)."""
        if not os.path.isdir(self.root):
            return []
        names = []
        for name in sorted(os.listdir(self.root)):
            path = os.path.join(self.root, name)
            if os.path.basename(path).startswith("."):
                continue
            if _is_kb_dir(path):
                names.append(name)
        return names

    def record(self, name: str) -> Optional[KbRecord]:
        raw = self._load_raw().get(name)
        return KbRecord.from_dict(name, raw) if isinstance(raw, dict) else None

    def registered_names(self) -> List[str]:
        """Kbs softwiki currently acknowledges.

        A directory that exists but has no registry entry counts as registered:
        that is the state of every deployment predating this module.
        """
        raw = self._load_raw()
        out = []
        for name in self.all_kbs():
            entry = raw.get(name)
            if entry is None:
                out.append(name)
            elif KbRecord.from_dict(name, entry).registered:
                out.append(name)
        return out

    def is_registered(self, name: str) -> bool:
        return name in self.registered_names()

    def records(self) -> List[dict]:
        raw = self._load_raw()
        rows = []
        for name in self.all_kbs():
            entry = raw.get(name) or {}
            record = KbRecord.from_dict(name, entry if isinstance(entry, dict) else {})
            rows.append({"name": name, **record.to_dict()})
        return rows

    # -- mutations -------------------------------------------------------

    def register(
        self,
        name: str,
        *,
        description: str = "",
        template: str = "generic",
        language: Optional[str] = None,
        created_by: Optional[str] = None,
        notes: str = "",
    ) -> KbRecord:
        path = os.path.join(self.root, name)
        if not _is_kb_dir(path):
            raise FileNotFoundError(f"kb '{name}' has no initialised directory")

        raw = self._load_raw()
        existing = raw.get(name) if isinstance(raw.get(name), dict) else {}
        record = KbRecord.from_dict(name, existing)
        record.status = STATUS_REGISTERED
        record.description = description or record.description
        record.template = template or record.template
        record.language = language or record.language
        record.created_at = record.created_at or _now()
        record.created_by = record.created_by or created_by
        record.unregistered_at = None
        record.unregistered_by = None
        record.notes = notes or record.notes
        raw[name] = record.to_dict()
        self._save_raw(raw)
        return record

    def unregister(self, name: str, *, unregistered_by: Optional[str] = None) -> KbRecord:
        """Unhook a kb from softwiki. Data on disk is untouched."""
        raw = self._load_raw()
        existing = raw.get(name) if isinstance(raw.get(name), dict) else {}
        record = KbRecord.from_dict(name, existing)
        record.status = STATUS_UNREGISTERED
        record.unregistered_at = _now()
        record.unregistered_by = unregistered_by
        raw[name] = record.to_dict()
        self._save_raw(raw)
        return record


# -- creation ------------------------------------------------------------


@dataclass
class PlanStep:
    kind: str
    description: str
    path: Optional[str] = None
    exists: bool = False


@dataclass
class CreatePlan:
    """A dry-run description of what creating a kb would do."""

    name: str
    template: str = "generic"
    description: str = ""
    language: Optional[str] = "zh"
    steps: List[PlanStep] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "template": self.template,
            "description": self.description,
            "language": self.language,
            "steps": [
                {
                    "kind": s.kind,
                    "description": s.description,
                    "path": s.path,
                    "exists": s.exists,
                }
                for s in self.steps
            ],
            "warnings": list(self.warnings),
        }


def validate_kb_name(name: str) -> str:
    """kb names double as directory names and appear in URLs."""
    value = (name or "").strip()
    if not value:
        raise ValueError("kb name is required")
    if len(value) > 64:
        raise ValueError("kb name is longer than 64 characters")
    if value.startswith("."):
        raise ValueError("kb name must not start with a dot")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
    bad = sorted(set(value) - allowed)
    if bad:
        raise ValueError(f"kb name contains unsupported characters: {''.join(bad)}")
    return value


def template_dir(template: str) -> Optional[str]:
    """Resolve a template to its directory on disk.

    Templates live at ``<repository>/kb-templates/<name>``. A template with no
    directory is still valid — creation falls back to the built-in defaults —
    but callers can tell the difference through this function.
    """
    if template not in BUILTIN_TEMPLATES:
        raise ValueError(f"unknown template {template!r}; choose from {list(BUILTIN_TEMPLATES)}")
    base = os.getenv("SOFTWIKI_KB_TEMPLATES_DIR") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        TEMPLATES_DIR,
    )
    candidate = os.path.join(base, template)
    return candidate if os.path.isdir(candidate) else None


def plan_create(
    name: str,
    *,
    template: str = "generic",
    description: str = "",
    language: Optional[str] = "zh",
    root: Optional[str] = None,
) -> CreatePlan:
    """Describe what :func:`create_kb` would write. Never touches disk."""
    root = root or get_workspaces_root()
    validated = validate_kb_name(name)
    template_dir(template)  # raises on unknown template

    kb_path = os.path.join(root, validated)
    plan = CreatePlan(
        name=validated,
        template=template,
        description=description,
        language=language,
    )

    exists = os.path.exists(kb_path)
    plan.steps = [
        PlanStep(
            kind="directory",
            description=f"create knowledge base directory {validated}",
            path=kb_path,
            exists=exists,
        ),
        PlanStep(
            kind="config",
            description="write config/meta.yaml (name, description, template)",
            path=os.path.join(kb_path, "config", "meta.yaml"),
        ),
        PlanStep(
            kind="config",
            description="write config/topics.yaml from the template",
            path=os.path.join(kb_path, "config", "topics.yaml"),
        ),
        PlanStep(
            kind="scope",
            description="write scope.md (first paragraph becomes the kb description fallback)",
            path=os.path.join(kb_path, "scope.md"),
        ),
        PlanStep(
            kind="index",
            description="create .softwiki/index so the kb is discoverable",
            path=os.path.join(kb_path, ".softwiki", "index"),
        ),
        PlanStep(
            kind="registry",
            description="register the kb in config/kbs.yaml",
            path=os.path.join(root, "config", REGISTRY_FILE),
        ),
    ]

    if exists:
        plan.warnings.append(
            f"{validated} already exists; writing will only fill in missing config files"
        )
    if not description:
        plan.warnings.append(
            "no description: agents will fall back to scope.md, then to topic groups"
        )
    if not os.path.isdir(os.path.join(root, "config")):
        plan.warnings.append("workspaces root has no config/ directory yet; it will be created")

    return plan


DEFAULT_TOPICS = {
    "general": {
        "name": "General",
        "group": "Topics",
        "description": "Uncategorised material; refine topics.yaml as the corpus grows.",
        "synonyms": [],
    }
}

GENERIC_SCOPE = """# {name}

{description}

This knowledge base was created from the `{template}` template. Edit this file to
describe what belongs in it: the first paragraph is shown to agents in
`kb_describe` when `config/meta.yaml` has no description.
"""


def create_kb(
    plan: CreatePlan,
    *,
    created_by: Optional[str] = None,
    root: Optional[str] = None,
    overwrite_topics: bool = False,
    provision_database: bool = True,
) -> dict:
    """Execute a :class:`CreatePlan`. Returns a summary of what was written."""
    root = root or get_workspaces_root()
    name = plan.name
    kb_path = os.path.join(root, name)
    written: List[str] = []

    tpl_dir = template_dir(plan.template)
    os.makedirs(os.path.join(kb_path, ".softwiki", "index"), exist_ok=True)
    os.makedirs(os.path.join(kb_path, "config"), exist_ok=True)
    os.makedirs(os.path.join(kb_path, "raw"), exist_ok=True)

    meta_path = os.path.join(kb_path, "config", "meta.yaml")
    meta = {}
    if os.path.isfile(meta_path):
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = yaml.safe_load(f) or {}
        except yaml.YAMLError as exc:
            logger.warning("meta.yaml for %s is unreadable, rewriting: %s", name, exc)
            meta = {}
    meta.setdefault("name", name)
    if plan.description:
        meta["description"] = plan.description
    meta.setdefault("template", plan.template)
    if plan.language:
        meta.setdefault("language", plan.language)
    with open(meta_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(meta, f, allow_unicode=True, sort_keys=False)
    written.append(meta_path)

    topics_path = os.path.join(kb_path, "config", "topics.yaml")
    if overwrite_topics or not os.path.isfile(topics_path):
        topics = DEFAULT_TOPICS
        if tpl_dir and os.path.isfile(os.path.join(tpl_dir, "topics.yaml")):
            with open(os.path.join(tpl_dir, "topics.yaml"), encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
            # Templates may wrap the mapping in a top-level "topics:" key.
            if isinstance(loaded, dict) and isinstance(loaded.get("topics"), dict):
                loaded = loaded["topics"]
            if isinstance(loaded, dict) and loaded:
                topics = loaded
        with open(topics_path, "w", encoding="utf-8") as f:
            yaml.safe_dump({"topics": topics}, f, allow_unicode=True, sort_keys=False)
        written.append(topics_path)

    scope_path = os.path.join(kb_path, "scope.md")
    if not os.path.isfile(scope_path):
        body = GENERIC_SCOPE.format(
            name=name, description=plan.description or "", template=plan.template
        )
        if tpl_dir and os.path.isfile(os.path.join(tpl_dir, "scope.md")):
            with open(os.path.join(tpl_dir, "scope.md"), encoding="utf-8") as f:
                body = f.read().replace("{name}", name).replace(
                    "{description}", plan.description or ""
                )
        with open(scope_path, "w", encoding="utf-8") as f:
            f.write(body)
        written.append(scope_path)

    # Optional seed: every new kb gets the deployment's model profile file, so
    # it does not silently fall back to the instance default provider (which is
    # how a new kb ended up on a depleted Gemini account while the others were
    # already on DeepSeek).
    seed = os.getenv("SOFTWIKI_KB_MODEL_PROFILES")
    if seed and os.path.isfile(seed):
        dest = os.path.join(kb_path, "config", "model_profiles.yaml")
        if not os.path.isfile(dest):
            import shutil

            shutil.copyfile(seed, dest)
            written.append(dest)

    KbRegistry(root).register(
        name,
        description=plan.description,
        template=plan.template,
        language=plan.language,
        created_by=created_by,
    )
    written.append(KbRegistry(root).path)

    database = {"created": False, "error": "provisioning disabled", "database": None}
    if provision_database:
        # A directory without a database is listed but not selectable, which is
        # indistinguishable from a broken kb in the UI. Provision it here and
        # report the outcome instead of leaving the user to guess.
        from softwiki.kb.provision import ensure_kb_database

        database = ensure_kb_database(kb_path)
        if not database.get("created"):
            logger.warning("kb %s created but database provisioning failed: %s", name, database.get("error"))

    return {"name": name, "written": written, "database": database}


def delete_kb_dir(name: str, *, root: Optional[str] = None) -> None:
    """Physically remove a kb directory.

    Deliberately *not* wired to any endpoint: softwiki unhooks knowledge bases
    (see :meth:`KbRegistry.unregister`), it does not delete data. Kept here so
    an operator script has one obvious place to call, with the guard rails.
    """
    root = root or get_workspaces_root()
    target = os.path.join(root, validate_kb_name(name))
    if os.path.dirname(os.path.abspath(target)) != os.path.abspath(root):
        raise ValueError("refusing to delete outside the workspaces root")
    if not _is_kb_dir(target):
        raise FileNotFoundError(target)
    shutil.rmtree(target)
