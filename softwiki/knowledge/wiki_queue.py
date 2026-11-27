"""Durable WikiArtifact rebuild queue + in-process worker.

The API container runs one uvicorn process; a daemon thread processes pending
tasks. Tasks are coalesced per topic and survive restarts.
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timedelta
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
            kind="topic",
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
    heartbeat_stop = threading.Event()
    heartbeat = threading.Thread(target=_heartbeat, args=(task.id, heartbeat_stop), daemon=True)
    heartbeat.start()
    try:
        return _run_claimed(db, task, generator)
    finally:
        heartbeat_stop.set()


def _run_claimed(db: Session, task: WikiRebuildTask, generator=None) -> dict:
    if getattr(task, "kind", "topic") == "subject":
        from softwiki.wiki.subject_pages import generate_subject_pages

        try:
            generate_subject_pages(db, task.topic)
            finish_task(db, task, None)
            return {"topic": task.topic, "kind": "subject", "status": "done",
                    "attempts": task.attempts}
        except Exception as exc:  # noqa: BLE001 - one bad subject must not stop the queue
            if _pause_task_for_provider(db, task, exc):
                return {"topic": task.topic, "kind": "subject", "status": "paused",
                        "attempts": task.attempts, "error": str(exc)[:200]}
            finish_task(db, task, str(exc))
            return {"topic": task.topic, "kind": "subject", "status": task.status,
                    "attempts": task.attempts, "error": str(exc)}

    if generator is None:
        from softwiki.wiki.page_generator import WikiPageGenerator
        generator = WikiPageGenerator()
    try:
        generator.generate_topic_page(db, task.topic, force_rebuild=True)
        finish_task(db, task, None)
        return {"topic": task.topic, "status": "done", "attempts": task.attempts}
    except Exception as exc:
        if _pause_task_for_provider(db, task, exc):
            return {"topic": task.topic, "status": "paused",
                    "attempts": task.attempts, "error": str(exc)[:200]}
        finish_task(db, task, str(exc))
        return {"topic": task.topic, "status": task.status, "attempts": task.attempts, "error": str(exc)}


def pending_count(db: Session) -> dict:
    return {
        "pending": db.query(WikiRebuildTask).filter(WikiRebuildTask.status == "pending").count(),
        "running": db.query(WikiRebuildTask).filter(WikiRebuildTask.status == "running").count(),
        "failed": db.query(WikiRebuildTask).filter(WikiRebuildTask.status == "failed").count(),
        "done": db.query(WikiRebuildTask).filter(WikiRebuildTask.status == "done").count(),
    }


RECONCILE_INTERVAL_SECONDS = float(os.getenv("WIKI_RECONCILE_INTERVAL_SECONDS", "300"))
# A task whose heartbeat stopped (container restart mid-generation, crash) used
# to stay "running" forever and was never retried. Reap it after this window.
STALE_RUNNING_MINUTES = float(os.getenv("WIKI_TASK_STALE_MINUTES", "30"))
# Concurrency and bulk backfill are opt-in so small deployments keep one worker.
WORKER_CONCURRENCY = max(1, int(os.getenv("WIKI_WORKER_CONCURRENCY", "1")))
AUTO_ENQUEUE_MISSING = os.getenv("WIKI_AUTO_ENQUEUE_MISSING", "").lower() in ("1", "true", "yes")
AUTO_ENQUEUE_LIMIT = max(1, int(os.getenv("WIKI_AUTO_ENQUEUE_LIMIT", "100")))
# A dead LLM provider (403 quota, 401 bad key) fails instantly; without this
# window the backfill would re-enqueue the same subjects every tick and fill
# the queue with thousands of failures.
BACKFILL_RETRY_HOURS = float(os.getenv("WIKI_BACKFILL_RETRY_HOURS", "6"))
REQUEUE_RUNNING_ON_START = os.getenv("WIKI_REQUEUE_RUNNING_ON_START", "").lower() in ("1", "true", "yes")
HEARTBEAT_SECONDS = float(os.getenv("WIKI_TASK_HEARTBEAT_SECONDS", "60"))


def reap_stale_running(db: Session, stale_minutes: Optional[float] = None) -> dict:
    """Requeue (or fail) tasks whose running heartbeat went stale.

    Called at worker start and on every reconcile tick, so a container restart
    during generation cannot strand tasks.
    """
    minutes = STALE_RUNNING_MINUTES if stale_minutes is None else stale_minutes
    cutoff = datetime.utcnow() - timedelta(minutes=minutes)
    rows = (
        db.query(WikiRebuildTask)
        .filter(WikiRebuildTask.status == "running")
        .filter(
            (WikiRebuildTask.updated_at.is_(None))
            | (WikiRebuildTask.updated_at < cutoff)
        )
        .all()
    )
    requeued = failed = 0
    now = datetime.utcnow()
    for row in rows:
        if (row.attempts or 0) < (row.max_attempts or 2):
            row.status = "pending"
            requeued += 1
        else:
            row.status = "failed"
            row.finished_at = now
            failed += 1
        row.error = "stale running task reaped (no heartbeat)"
        row.updated_at = now
    if rows:
        db.commit()
        print(f"[wiki-worker] reaped {requeued} stale running task(s), "
              f"failed {failed}", flush=True)
    return {"reaped": requeued + failed, "requeued": requeued, "failed": failed}


def requeue_running_on_start(db: Session) -> int:
    """On process start, put every `running` task back to pending.

    Safe for the single-worker/single-instance deployment we run today: the
    previous process is gone, so nothing can still be working on those rows.
    Multi-instance deployments must leave WIKI_REQUEUE_RUNNING_ON_START off.
    """
    rows = db.query(WikiRebuildTask).filter(WikiRebuildTask.status == "running").all()
    now = datetime.utcnow()
    for row in rows:
        row.status = "pending"
        row.error = "requeued on worker start"
        row.updated_at = now
    if rows:
        db.commit()
        print(f"[wiki-worker] requeued {len(rows)} running task(s) on start", flush=True)
    return len(rows)


def enqueue_missing_subjects(db: Session, limit: int = AUTO_ENQUEUE_LIMIT,
                             min_relations: int = 5) -> int:
    """Queue subject pages for candidates that have no page yet.

    This is what makes a bulk backfill durable: the list lives in the DB, so a
    restart resumes instead of losing an in-memory loop.
    """
    from softwiki.intelligence.llm_health import breaker

    if breaker.is_open():
        print("[wiki-worker] provider breaker open; skip backfill enqueue", flush=True)
        return 0

    from softwiki.wiki.auto_pages import _pending_subjects, enqueue_subject
    from softwiki.wiki.subject_pages import list_generated_pages, subject_candidates

    candidates = subject_candidates(db, min_relations=min_relations, use_cache=False)
    have = {s.get("subject") for s in list_generated_pages(db).get("subjects", [])}
    queued = _pending_subjects(db)
    cutoff = datetime.utcnow() - timedelta(hours=BACKFILL_RETRY_HOURS)
    recently_failed = {
        row[0]
        for row in db.query(WikiRebuildTask.topic)
        .filter(
            WikiRebuildTask.kind == "subject",
            WikiRebuildTask.status == "failed",
            WikiRebuildTask.created_at >= cutoff,
        )
        .all()
    }
    created = 0
    for cand in candidates:
        subject = cand["subject"]
        if subject in have or subject in queued or subject in recently_failed:
            continue
        if enqueue_subject(db, subject, reason="backfill"):
            created += 1
            queued.add(subject)
        if created >= limit:
            break
    if created:
        db.commit()
        print(f"[wiki-worker] enqueued {created} missing subject(s)", flush=True)
    return created


def _provider_paused() -> bool:
    from softwiki.intelligence.llm_health import breaker
    return breaker.is_open()


def _pause_task_for_provider(db: Session, task: WikiRebuildTask, exc: BaseException) -> bool:
    """If the failure is an LLM provider problem, keep the task pending.

    Marking it failed would waste an attempt and make the failure look like bad
    data; the breaker already prevents new work until the cooldown expires.
    """
    from softwiki.intelligence.llm_health import breaker, is_fatal

    fatal = is_fatal(exc)
    if fatal and not breaker.is_open():
        # The call may not have gone through create_chat_completion (e.g. an
        # adapter); still make the failure visible and stop the queue.
        breaker.record_failure(exc)
    if not (breaker.is_open() or fatal):
        return False
    task.status = "pending"
    task.error = f"provider paused: {exc}"[:2000]
    task.updated_at = datetime.utcnow()
    db.commit()
    return True


def _heartbeat(task_id: int, stop_event: threading.Event) -> None:
    from softwiki.source_store.db import SessionLocal

    while not stop_event.wait(HEARTBEAT_SECONDS):
        db = SessionLocal()
        try:
            db.query(WikiRebuildTask).filter(WikiRebuildTask.id == task_id).update(
                {"updated_at": datetime.utcnow()}
            )
            db.commit()
        except Exception as exc:  # noqa: BLE001 - heartbeat must not kill the task
            print(f"[wiki-worker] heartbeat failed for task {task_id}: {exc}", flush=True)
        finally:
            db.close()


def _available_kbs() -> list:
    """Every initialised kb in this instance (``[None]`` = the default one).

    The worker is started once per process, outside any request, so it has no
    kb context. Without iterating, only the instance's default workspace ever
    got its wiki rebuilt — tasks enqueued for any other kb sat in their own
    database forever.
    """
    try:
        from softwiki.config import get_workspaces_root
        from softwiki.kb.registry import list_kb_infos

        names = [info.name for info in list_kb_infos(get_workspaces_root())]
    except Exception as exc:  # noqa: BLE001 - fall back to the default workspace
        print(f"[wiki-worker] kb discovery skipped: {exc}", flush=True)
        names = []
    return names or [None]


def _enter(kb):
    if kb is None:
        return None
    from softwiki.kb.context import enter_kb

    return enter_kb(kb)


def _leave(token) -> None:
    if token is None:
        return
    from softwiki.kb.context import restore_kb

    restore_kb(token)


def _worker_loop(stop_event: Optional[threading.Event] = None, kbs: Optional[list] = None):
    """Claim and process one task per iteration, round-robin over kbs."""
    from softwiki.source_store.db import SessionLocal

    names = kbs or [None]
    index = 0
    while not (stop_event and stop_event.is_set()):
        if _provider_paused():
            time.sleep(30)
            continue
        kb = names[index % len(names)]
        index += 1
        token = _enter(kb)
        try:
            db = SessionLocal()
            try:
                result = run_once(db)
            finally:
                db.close()
        except Exception as exc:  # noqa: BLE001 - one bad task must not stop the pool
            print(f"[wiki-worker] loop error ({kb}): {exc}", flush=True)
            result = None
        finally:
            _leave(token)
        time.sleep(2 if result else 5)


def worker_loop(stop_event: Optional[threading.Event] = None) -> None:
    """Start N worker threads plus one reconcile/backfill leader.

    Restart safety: tasks are durable rows. With
    ``WIKI_REQUEUE_RUNNING_ON_START=1`` a restart puts orphaned `running` rows
    back to `pending` immediately; with ``WIKI_AUTO_ENQUEUE_MISSING=1`` the
    leader keeps topping the queue up with missing subject candidates, so a
    bulk backfill continues across deploys without an external process.
    """
    from softwiki.source_store.db import SessionLocal

    kbs = _available_kbs()
    for kb in kbs:
        token = _enter(kb)
        db = SessionLocal()
        try:
            if REQUEUE_RUNNING_ON_START:
                requeue_running_on_start(db)
            if AUTO_ENQUEUE_MISSING:
                enqueue_missing_subjects(db)
        except Exception as exc:  # noqa: BLE001 - startup must not kill the app
            print(f"[wiki-worker] startup recovery skipped for {kb}: {exc}", flush=True)
        finally:
            db.close()
            _leave(token)

    concurrency = WORKER_CONCURRENCY
    try:
        from softwiki.config import get_db_url

        if get_db_url().startswith("sqlite"):
            # SQLite has no SKIP LOCKED; concurrent claimers would double-run.
            concurrency = 1
    except Exception:  # noqa: BLE001 - keep the configured value on failure
        pass
    for index in range(concurrency):
        threading.Thread(
            target=_worker_loop,
            args=(None, kbs),
            name=f"wiki-worker-{index + 1}",
            daemon=True,
        ).start()
    print(f"[wiki-worker] {concurrency} worker(s) started", flush=True)

    # The calling thread becomes the leader: reconcile + periodic backfill.
    last_reconcile = 0.0
    while not (stop_event and stop_event.is_set()):
        now = time.monotonic()
        if now - last_reconcile >= RECONCILE_INTERVAL_SECONDS:
            last_reconcile = now
            # New kbs can appear without a restart.
            kbs = _available_kbs()
            for kb in kbs:
                token = _enter(kb)
                db = SessionLocal()
                try:
                    reap_stale_running(db)
                    if AUTO_ENQUEUE_MISSING:
                        enqueue_missing_subjects(db)
                    from softwiki.wiki.auto_pages import reconcile

                    queued = reconcile(db, allow_initial=False)
                    if queued.get("enqueued"):
                        print(f"[wiki-worker] queued {queued['enqueued']} changed subject(s) in {kb}",
                              flush=True)
                except Exception as exc:  # noqa: BLE001 - never kill the worker
                    print(f"[wiki-worker] reconcile skipped for {kb}: {exc}", flush=True)
                finally:
                    db.close()
                    _leave(token)
        time.sleep(5)
