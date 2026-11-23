"""Auto-generate subject pages from claim changes.

Two triggers, one budget:

* **New knowledge base** — the first reconcile finds claims but no generated
  pages, so it enqueues the top ``WIKI_AUTO_INITIAL_SUBJECTS`` subjects. That is
  what makes a freshly built kb readable without anyone clicking Generate 400
  times.
* **Changed subjects** — once pages exist, only subjects whose claim count moved
  are rebuilt. A new subject is *not* auto-created (otherwise a single ingest
  could spawn dozens of pages nobody asked for).

Both are capped per run (``WIKI_AUTO_MAX_SUBJECTS``) so a large import cannot
saturate the queue. The work itself goes through the same durable queue the
topic pages use, so it survives restarts.
"""

from __future__ import annotations

import os
from typing import Optional

from sqlalchemy.orm import Session

from softwiki.source_store.models import WikiRebuildTask


def _budget(initial: bool) -> int:
    key = "WIKI_AUTO_INITIAL_SUBJECTS" if initial else "WIKI_AUTO_MAX_SUBJECTS"
    default = "20"
    try:
        return max(0, int(os.getenv(key, default)))
    except ValueError:
        return int(default)


def _pending_subjects(db: Session) -> set[str]:
    rows = (
        db.query(WikiRebuildTask.topic)
        .filter(WikiRebuildTask.kind == "subject", WikiRebuildTask.status.in_(("pending", "running")))
        .all()
    )
    return {r[0] for r in rows}


def enqueue_subject(db: Session, subject: str, reason: str = "auto") -> bool:
    """Queue one subject page rebuild unless it is already queued."""
    exists = (
        db.query(WikiRebuildTask.id)
        .filter(
            WikiRebuildTask.kind == "subject",
            WikiRebuildTask.topic == subject,
            WikiRebuildTask.status.in_(("pending", "running")),
        )
        .first()
    )
    if exists:
        return False
    db.add(WikiRebuildTask(topic=subject, kind="subject", reason=reason, status="pending"))
    return True


def reconcile(db: Session, budget: Optional[int] = None, allow_initial: bool = True) -> dict:
    """Compare generated pages against the current graph and queue the deltas.

    ``allow_initial=False`` never bootstraps: a kb with no pages waits for the
    user to press the button in the UI. Incremental rebuilds (pages already
    exist) always run, because the user should not have to babysit them.
    """
    from softwiki.wiki.subject_pages import list_generated_pages, subject_candidates

    listing = list_generated_pages(db)
    generated = {s.get("subject"): s for s in listing.get("subjects", [])}
    initial = not generated

    if initial and not allow_initial:
        return {"enqueued": 0, "initial": True, "needs_start": True}

    limit = _budget(initial) if budget is None else max(0, budget)
    if limit == 0:
        return {"enqueued": 0, "initial": initial, "skipped": "budget is 0"}

    candidates = subject_candidates(db, limit=600, use_cache=False)
    pending = _pending_subjects(db)

    enqueued: list[str] = []
    for cand in candidates:
        if len(enqueued) >= limit:
            break
        subject = cand["subject"]
        if subject in pending:
            continue
        if initial:
            enqueued.append(subject)
        else:
            page = generated.get(subject)
            if page and page.get("claims_total") != cand["claims_total"]:
                enqueued.append(subject)

    created = 0
    for subject in enqueued:
        if enqueue_subject(db, subject, reason="auto_initial" if initial else "claims_changed"):
            created += 1
    if created:
        db.commit()
    return {
        "enqueued": created,
        "initial": initial,
        "considered": len(candidates),
        "budget": limit,
        "subjects": enqueued[:20],
    }
