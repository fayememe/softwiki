"""Per-kb rules for entity pages: ignore and lock.

Two problems this solves, both found on a real corpus:

* **Meaningless subjects.** In armkb the entity `Arm` matches 1,110 claims
  because every document is about Arm the company. A page for it would just
  restate the corpus. `ignore` removes such subjects from the candidate list and
  from auto-rebuilds.
* **Hand-written pages.** Some pages are worth editing by hand. `locked` keeps
  the generator away so the edit survives the next rebuild.

Stored next to the other kb config so an operator can diff and edit it:

    config/wiki_subjects.yaml
    ignore:
      - Arm
      - ARM Limited
    locked:
      - Cortex-M55
"""

from __future__ import annotations

import os
from typing import Iterable

import yaml


def _path() -> str:
    from softwiki.config import get_config_path

    return get_config_path("wiki_subjects.yaml")


def load() -> dict:
    path = _path()
    if not os.path.isfile(path):
        return {"ignore": [], "locked": []}
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as exc:  # noqa: BLE001 - a broken file must not break listing
        print(f"[wiki] ignoring unreadable {path}: {exc}", flush=True)
        return {"ignore": [], "locked": []}
    return {
        "ignore": [str(x) for x in (data.get("ignore") or [])],
        "locked": [str(x) for x in (data.get("locked") or [])],
    }


def save(ignore: Iterable[str], locked: Iterable[str]) -> dict:
    data = {
        "ignore": sorted({str(x).strip() for x in ignore if str(x).strip()}),
        "locked": sorted({str(x).strip() for x in locked if str(x).strip()}),
    }
    path = _path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    os.replace(tmp, path)
    return data


def ignored() -> set[str]:
    return set(load()["ignore"])


def locked() -> set[str]:
    return set(load()["locked"])


def add_ignore(subject: str) -> dict:
    rules = load()
    rules["ignore"] = sorted(set(rules["ignore"]) | {subject})
    return save(rules["ignore"], rules["locked"])


def remove_ignore(subject: str) -> dict:
    rules = load()
    rules["ignore"] = [s for s in rules["ignore"] if s != subject]
    return save(rules["ignore"], rules["locked"])


def set_locked(subject: str, value: bool) -> dict:
    rules = load()
    names = set(rules["locked"])
    if value:
        names.add(subject)
    else:
        names.discard(subject)
    return save(rules["ignore"], names)
