"""Propose → approve → execute, for wiki changes that need judgement.

The agent is good at *finding* candidates ("these 12 pages only restate the
corpus"); it should not be the thing that decides to delete them. So:

* the agent creates a **plan** (needs ``wiki.submit``),
* a human approves it (needs ``wiki.apply``),
* approval **executes the plan immediately** — the human should not have to redo
  the agent's work by hand, and the agent should not need to stay alive.

Every step is audited; the plan row is the record of who proposed what and who
allowed it.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from sqlalchemy.orm import Session

from softwiki.source_store.models import WikiActionPlan

#: Actions a plan may carry, and the capability needed to approve each.
ACTIONS = {
    "ignore_subjects": "wiki.apply",
    "delete_pages": "wiki.apply",
    "regenerate_subjects": "wiki.apply",
}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def create_plan(
    db: Session,
    kind: str,
    payload: dict,
    *,
    kb: Optional[str] = None,
    proposed_by: Optional[str] = None,
    reason: str = "",
) -> WikiActionPlan:
    if kind not in ACTIONS:
        raise ValueError(f"unknown plan kind {kind!r}")
    plan = WikiActionPlan(
        kb=kb,
        kind=kind,
        payload=_json(payload),
        status="pending",
        proposed_by=proposed_by,
        reason=reason,
    )
    db.add(plan)
    db.commit()
    return plan


def list_plans(db: Session, status: Optional[str] = None, limit: int = 50) -> list[WikiActionPlan]:
    q = db.query(WikiActionPlan)
    if status:
        q = q.filter(WikiActionPlan.status == status)
    return q.order_by(WikiActionPlan.created_at.desc()).limit(max(1, min(limit, 200))).all()


def get_plan(db: Session, plan_id: int) -> Optional[WikiActionPlan]:
    return db.query(WikiActionPlan).filter(WikiActionPlan.id == plan_id).first()


def _delete_pages(db: Session, subjects: list[str]) -> dict:
    """Remove generated pages (and their index entries) for the given subjects."""
    from softwiki.config import get_export_dir
    from softwiki.wiki.subject_pages import invalidate_candidates

    pages_dir = get_export_dir("wiki/pages")
    index_path = os.path.join(pages_dir, "index.json")
    data = {"subjects": []}
    if os.path.exists(index_path):
        try:
            with open(index_path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            data = {"subjects": []}

    wanted = set(subjects)
    keep, removed = [], []
    for entry in data.get("subjects", []):
        if entry.get("subject") in wanted:
            for slug in entry.get("pages", []):
                path = os.path.join(pages_dir, f"{slug}.md")
                if os.path.exists(path):
                    os.remove(path)
            removed.append(entry["subject"])
        else:
            keep.append(entry)
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({"subjects": keep}, f, ensure_ascii=False, indent=2)

    invalidate_candidates()
    return {"removed": removed, "remaining_subjects": len(keep)}


def _ignore_subjects(db: Session, subjects: list[str]) -> dict:
    from softwiki.wiki import subject_rules

    for subject in subjects:
        subject_rules.add_ignore(subject)
    return _delete_pages(db, subjects)


def _regenerate_subjects(db: Session, subjects: list[str]) -> dict:
    from softwiki.wiki.subject_pages import generate_subject_pages

    results = []
    for subject in subjects:
        try:
            out = generate_subject_pages(db, subject, force=True)
            results.append({"subject": subject, "pages": len(out.get("pages", []))})
        except Exception as exc:  # noqa: BLE001 - report per subject, keep going
            results.append({"subject": subject, "error": str(exc)[:200]})
    return {"results": results}


_EXECUTORS = {
    "ignore_subjects": _ignore_subjects,
    "delete_pages": _delete_pages,
    "regenerate_subjects": _regenerate_subjects,
}


def decide(db: Session, plan: WikiActionPlan, approve: bool, *,
           decided_by: Optional[str] = None, reason: str = "") -> dict:
    """Approve (and execute) or reject a plan."""
    if plan.status != "pending":
        raise ValueError(f"plan {plan.id} is already {plan.status}")

    plan.decided_at = _now()
    plan.approved_by = decided_by
    if reason:
        plan.reason = (plan.reason + "\n" + reason).strip() if plan.reason else reason

    if not approve:
        plan.status = "rejected"
        db.commit()
        return {"status": "rejected", "plan_id": plan.id}

    payload = json.loads(plan.payload or "{}")
    subjects = payload.get("subjects") or []
    executor = _EXECUTORS.get(plan.kind)
    if executor is None:
        plan.status = "failed"
        plan.result = _json({"error": f"no executor for {plan.kind}"})
        db.commit()
        raise ValueError(f"no executor for {plan.kind}")

    try:
        result = executor(db, subjects)
    except Exception as exc:  # noqa: BLE001 - record, do not crash the request
        plan.status = "failed"
        plan.result = _json({"error": str(exc)[:500]})
        db.commit()
        return {"status": "failed", "plan_id": plan.id, "error": str(exc)[:200]}

    plan.status = "applied"
    plan.applied_at = _now()
    plan.result = _json(result)
    db.commit()
    return {"status": "applied", "plan_id": plan.id, **result}


def _now():
    from datetime import datetime

    return datetime.utcnow()
