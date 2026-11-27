"""The wiki worker must serve every kb, not just the default workspace.

It starts once per process, outside any request, so it has no kb context. Before
this it always opened the instance's default database: rebuild tasks enqueued
for any other kb sat in their own database and never ran.
"""

import threading


def test_worker_loop_cycles_through_kbs(monkeypatch):
    import softwiki.knowledge.wiki_queue as q

    seen = []
    stop = threading.Event()

    def fake_enter(kb):
        seen.append(kb)
        return kb

    calls = {"n": 0}

    def fake_run_once(_db):
        calls["n"] += 1
        if calls["n"] >= 3:
            stop.set()
        return None

    monkeypatch.setattr(q, "_enter", fake_enter)
    monkeypatch.setattr(q, "_leave", lambda token: None)
    monkeypatch.setattr(q, "_provider_paused", lambda: False)
    monkeypatch.setattr(q, "run_once", fake_run_once)
    monkeypatch.setattr(q.time, "sleep", lambda _s: None)

    import softwiki.source_store.db as dbmod

    class _S:
        def close(self):
            pass

    monkeypatch.setattr(dbmod, "SessionLocal", lambda: _S())

    q._worker_loop(stop, ["kb-a", "kb-b"])

    assert seen[:3] == ["kb-a", "kb-b", "kb-a"] or seen[:3] == ["kb-a", "kb-b", None]


def test_available_kbs_falls_back_to_default(monkeypatch):
    import softwiki.knowledge.wiki_queue as q

    monkeypatch.setattr(
        "softwiki.kb.registry.list_kb_infos",
        lambda _root: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert q._available_kbs() == [None]
