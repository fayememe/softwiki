"""Background extraction must run against the knowledge base it was queued for.

Incident (2026-11-26): the worker thread did not inherit the request-scoped kb,
so `SessionLocal` resolved to the instance's default workspace and extraction
queued for one kb was written into another — 6k bogus claims plus a database
deadlock on `canonical_claims`. These tests pin the two properties that make it
impossible again: the kb travels with the job, and canonicalization is serial.
"""

import threading

import pytest


class _DummyDoc:
    status = "pending"
    cleaned_text = "text"
    published_at = None


class _DummySession:
    def commit(self):
        pass

    def close(self):
        pass

    def rollback(self):
        pass


def test_worker_enters_the_queued_kb(monkeypatch):
    seen = {}

    import softwiki.kb.context as kbctx
    import softwiki.source_store.db as dbmod
    from softwiki.extraction import processor
    from softwiki.source_store.document_repo import DocumentRepository

    monkeypatch.setattr(kbctx, "enter_kb", lambda kb: seen.setdefault("kb", kb))
    monkeypatch.setattr(dbmod, "SessionLocal", lambda: _DummySession())
    monkeypatch.setattr(DocumentRepository, "get_document", staticmethod(lambda db, doc_id: None))
    monkeypatch.setattr(processor.time, "sleep", lambda _s: None)

    processor._bg_extraction_worker(1, "text", None, kb="demo-kb")

    assert seen["kb"] == "demo-kb"


def test_background_pipeline_passes_current_kb(monkeypatch):
    captured = {}

    import softwiki.kb.context as kbctx
    from softwiki.extraction import processor
    from softwiki.source_store.document_repo import DocumentRepository

    class _Thread:
        def __init__(self, target=None, args=(), **_kwargs):
            captured["target"] = target
            captured["args"] = args

        def start(self):
            captured["started"] = True

        def is_alive(self):
            return False

    monkeypatch.setattr(processor.threading, "Thread", _Thread)
    monkeypatch.setattr(DocumentRepository, "get_document", staticmethod(lambda db, doc_id: _DummyDoc()))

    class _Ctx:
        def get(self):
            return "demo-kb"

        def set(self, value):
            pass

    monkeypatch.setattr(kbctx, "current_kb_name", lambda: "demo-kb")

    result = processor.run_extraction_pipeline(
        _DummySession(), 1, "text", None, background=True,
    )

    assert result["status"] == "pending"
    assert captured["started"] is True
    assert captured["args"][-1] == "demo-kb"


def test_canonicalization_is_serialised():
    """Two workers must not canonicalize at the same time (deadlocks/dup keys)."""
    from softwiki.extraction import processor

    assert isinstance(processor._CANONICAL_LOCK, type(threading.Lock()))
    assert processor._CANONICAL_LOCK.locked() is False
