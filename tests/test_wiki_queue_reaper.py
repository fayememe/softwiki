"""Stale `running` wiki tasks must be recovered after a restart."""

from datetime import datetime, timedelta

import pytest


@pytest.fixture()
def db(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("WORKSPACE_DIR", str(ws))
    from softwiki.source_store.db import SessionLocal, get_engine, init_tables

    try:
        get_engine().dispose()
    except Exception:
        pass
    init_tables()
    session = SessionLocal()
    yield session
    session.close()
    try:
        get_engine().dispose()
    except Exception:
        pass


def _task(db, topic, status, minutes_old, attempts=1, max_attempts=2):
    from softwiki.source_store.models import WikiRebuildTask

    when = datetime.utcnow() - timedelta(minutes=minutes_old)
    task = WikiRebuildTask(
        topic=topic, kind="subject", status=status, attempts=attempts,
        max_attempts=max_attempts, created_at=when, updated_at=when,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def test_reap_requeues_stale_running(db):
    from softwiki.knowledge.wiki_queue import reap_stale_running

    task = _task(db, "SPE", "running", minutes_old=120)
    stats = reap_stale_running(db, stale_minutes=30)

    db.refresh(task)
    assert stats["requeued"] == 1
    assert task.status == "pending"
    assert "reaped" in (task.error or "")


def test_reap_fails_when_attempts_exhausted(db):
    from softwiki.knowledge.wiki_queue import reap_stale_running

    task = _task(db, "APB", "running", minutes_old=120, attempts=2, max_attempts=2)
    stats = reap_stale_running(db, stale_minutes=30)

    db.refresh(task)
    assert stats["failed"] == 1
    assert task.status == "failed"
    assert task.finished_at is not None


def test_reap_leaves_fresh_and_pending_alone(db):
    from softwiki.knowledge.wiki_queue import reap_stale_running

    fresh = _task(db, "P-Channel", "running", minutes_old=1)
    pending = _task(db, "amba", "pending", minutes_old=120)

    stats = reap_stale_running(db, stale_minutes=30)

    db.refresh(fresh)
    db.refresh(pending)
    assert stats["reaped"] == 0
    assert fresh.status == "running"
    assert pending.status == "pending"


def test_heartbeat_bumps_updated_at(db, monkeypatch):
    import softwiki.knowledge.wiki_queue as queue

    task = _task(db, "Helium", "running", minutes_old=10)
    before = task.updated_at
    monkeypatch.setattr(queue, "HEARTBEAT_SECONDS", 0.01)
    import threading

    stop = threading.Event()
    thread = threading.Thread(target=queue._heartbeat, args=(task.id, stop), daemon=True)
    thread.start()
    import time

    time.sleep(0.1)
    stop.set()
    thread.join(timeout=2)
    db.expire_all()
    refreshed = db.query(type(task)).filter_by(id=task.id).one()
    assert refreshed.updated_at > before
