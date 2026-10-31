"""Durable WikiArtifact rebuild queue + in-process worker.

The API container runs one uvicorn process; a daemon thread processes pending
tasks. Tasks are coalesced per topic and survive restarts.
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from softwiki.source_store.models import WikiArtifactState, WikiRebuildTask


def _page_topics(topics: Iterable[str]) -> set[str]:
    from softwiki.wiki.interventions import page_topics_for_claim_topic
    pages: set[str] = set()
    for topic in {t for t in topics if t}:
        pages.update(page_topics_for_claim_topic(topic))
    return pages


def enqueue_wiki_rebuild(db: Session, topics: Iterable[str], reason: str = "") -> int:
    """Enqueue page rebuilds; coalesce pending and running topics."""
    pages = _page_topics(topics)
    created = 0
    for topic in pages:
        pending = db.query(WikiRebuildTask).filter(
            WikiRebuildTask.topic == topic,
            WikiRebuildTask.status == "pending",
        ).first()
        if pending:
            continue
        running = db.query(WikiRebuildTask).filter(
            WikiRebuildTask.topic == topic,
            WikiRebuildTask.status == "running",
        ).first()
        # If running, queue one follow-up so a change during generation is not lost.
        task = WikiRebuildTask(
            topic=topic,
            reason=reason or "claim_changed",
            status="pending",
        )
        db.add(task)
        created += 1
    if created:
        db.commit()
    return created


def enqueue_stale_wiki(db: Session, reason: str = "manual_stale") -> int:
    rows = db.query(WikiArtifactState).filter(WikiArtifactState.stale_at.isnot(None)).all()
    return enqueue_wiki_rebuild(db, [r.topic for r in rows], reason=reason)


def claim_next(db: Session) -> Optional[WikiRebuildTask]:
    q = db.query(WikiRebuildTask).filter(WikiRebuildTask.status == "pending")
    try:
        q = q.with_for_update(skip_locked=True)
    except Exception:
        pass
    task = q.order_by(WikiRebuildTask.created_at.asc()).first()
    if task is None:
        return None
    task.status = "running"
    task.attempts = (task.attempts or 0) + 1
    task.started_at = datetime.utcnow()
    task.updated_at = datetime.utcnow()
    db.commit()
    return task


def finish_task(db: Session, task: WikiRebuildTask, error: Optional[str] = None) -> None:
    if error:
        if (task.attempts or 0) < (task.max_attempts or 2):
            task.status = "pending"
            task.error = error[:2000]
        else:
            task.status = "failed"
            task.error = error[:2000]
            task.finished_at = datetime.utcnow()
    else:
        task.status = "done"
        task.error = None
        task.finished_at = datetime.utcnow()
    task.updated_at = datetime.utcnow()
    db.commit()


def run_once(db: Session, generator=None) -> Optional[dict]:
    task = claim_next(db)
    if task is None:
        return None
    if generator is None:
        from softwiki.wiki.page_generator import WikiPageGenerator
        generator = WikiPageGenerator()
    try:
        generator.generate_topic_page(db, task.topic, force_rebuild=True)
        finish_task(db, task, None)
        return {"topic": task.topic, "status": "done", "attempts": task.attempts}
    except Exception as exc:
        finish_task(db, task, str(exc))
        return {"topic": task.topic, "status": task.status, "attempts": task.attempts, "error": str(exc)}


def pending_count(db: Session) -> dict:
    return {
        "pending": db.query(WikiRebuildTask).filter(WikiRebuildTask.status == "pending").count(),
        "running": db.query(WikiRebuildTask).filter(WikiRebuildTask.status == "running").count(),
        "failed": db.query(WikiRebuildTask).filter(WikiRebuildTask.status == "failed").count(),
        "done": db.query(WikiRebuildTask).filter(WikiRebuildTask.status == "done").count(),
    }


def worker_loop(stop_event: Optional[threading.Event] = None) -> None:
    from softwiki.source_store.db import SessionLocal
    while not (stop_event and stop_event.is_set()):
        db = SessionLocal()
        try:
            result = run_once(db)
        except Exception as exc:
            print(f"[wiki-worker] loop error: {exc}", flush=True)
            result = None
        finally:
            db.close()
        time.sleep(2 if result else 5)
