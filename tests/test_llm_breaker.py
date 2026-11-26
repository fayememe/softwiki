"""Fatal LLM errors must pause work, not mark every task failed."""

from datetime import datetime

import pytest


class FatalLLMError(RuntimeError):
    status_code = 403


class TransientLLMError(RuntimeError):
    status_code = 503


@pytest.fixture(autouse=True)
def fresh_breaker(monkeypatch):
    import softwiki.intelligence.llm_health as health

    b = health.ProviderBreaker()
    monkeypatch.setattr(health, "breaker", b)
    # modules imported the singleton lazily; clear cached references if any
    return b


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


def test_fatal_error_opens_breaker_and_blocks_calls(fresh_breaker, monkeypatch):
    from softwiki.intelligence import llm_client
    from softwiki.intelligence.llm_health import ProviderUnavailable

    class Client:
        class chat:
            class completions:
                calls = 0

                @staticmethod
                def create(**kwargs):
                    Client.chat.completions.calls += 1
                    raise FatalLLMError("预扣费额度失败")

    monkeypatch.setattr(llm_client, "breaker", fresh_breaker, raising=False)
    with pytest.raises(FatalLLMError):
        llm_client.create_chat_completion(Client(), attempts=3)
    assert Client.chat.completions.calls == 1  # fatal is not retried
    assert fresh_breaker.is_open()

    with pytest.raises(ProviderUnavailable):
        llm_client.create_chat_completion(Client())
    assert Client.chat.completions.calls == 1


def test_transient_errors_open_after_strikes(fresh_breaker):
    fresh_breaker.record_failure(TransientLLMError("504"))
    assert not fresh_breaker.is_open()
    fresh_breaker.record_failure(TransientLLMError("504"))
    fresh_breaker.record_failure(TransientLLMError("504"))
    assert fresh_breaker.is_open()


def test_success_resets_breaker(fresh_breaker):
    fresh_breaker.record_failure(FatalLLMError("quota"))
    assert fresh_breaker.is_open()
    fresh_breaker.record_success()
    assert not fresh_breaker.is_open()


def test_generation_failure_keeps_task_pending(db, fresh_breaker, monkeypatch):
    from softwiki.knowledge.wiki_queue import run_once
    from softwiki.source_store.models import WikiRebuildTask

    db.add(WikiRebuildTask(topic="amba", kind="topic", status="pending",
                           created_at=datetime.utcnow()))
    db.commit()

    class Generator:
        def generate_topic_page(self, *args, **kwargs):
            raise FatalLLMError("预扣费额度失败")

    result = run_once(db, generator=Generator())
    row = db.query(WikiRebuildTask).filter(WikiRebuildTask.topic == "amba").one()
    assert result["status"] == "paused"
    assert row.status == "pending"          # not failed
    assert row.attempts == 1
    assert fresh_breaker.is_open()


def test_enqueue_skipped_while_breaker_open(db, fresh_breaker):
    from softwiki.knowledge.wiki_queue import enqueue_missing_subjects

    fresh_breaker.open("quota", 600)
    assert enqueue_missing_subjects(db, limit=10) == 0
