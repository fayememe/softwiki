"""Query-time embedding must fail fast.

When the embedding provider is down, a search has to fall back to BM25 in
seconds. Indexing keeps the longer budget and retries, because losing a whole
batch is worse than waiting. Conflating the two turned every /api/ask into a
185-second stall (60s timeout x 3 attempts) before degrading.
"""

import os

import pytest

from softwiki.rag import embedder as emb


class _FakeClient:
    def __init__(self, fail: bool):
        self.fail = fail
        self.calls = 0
        self.timeout = None
        self.embeddings = self

    def create(self, **kwargs):
        self.calls += 1
        if self.fail:
            raise RuntimeError("provider down")
        return type("R", (), {"data": [type("D", (), {"embedding": [0.1, 0.2]})()]})()


@pytest.fixture()
def fake(monkeypatch):
    emb._openai_client = None
    emb._openai_query_client = None
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-v4")
    yield
    emb._openai_client = None
    emb._openai_query_client = None


def test_query_embedding_does_not_retry(fake, monkeypatch):
    client = _FakeClient(fail=True)
    monkeypatch.setattr(emb, "get_openai_client", lambda query=False: client)
    monkeypatch.setenv("EMBEDDING_MAX_RETRIES", "3")

    w = emb.WikiEmbedder()
    with pytest.raises(RuntimeError):
        w.embed_query("hello world")

    assert client.calls == 1, "a query must not retry: it delays BM25 fallback"


def test_batch_embedding_still_retries(fake, monkeypatch):
    client = _FakeClient(fail=True)
    monkeypatch.setattr(emb, "get_openai_client", lambda query=False: client)
    monkeypatch.setenv("EMBEDDING_MAX_RETRIES", "2")

    w = emb.WikiEmbedder()
    with pytest.raises(RuntimeError):
        w.embed_texts(["a", "b"])

    assert client.calls == 3, "indexing keeps its retries (1 + 2)"


def test_query_client_has_shorter_timeout(fake, monkeypatch):
    monkeypatch.setenv("EMBEDDING_TIMEOUT_SECONDS", "60")
    monkeypatch.delenv("EMBEDDING_QUERY_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setenv("EMBEDDING_API_KEY", "test-key")

    captured = {}

    class _Client:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("openai.OpenAI", _Client)
    emb.get_openai_client(query=True)

    assert captured["timeout"] <= 8.0, "query timeout must be small"
    assert captured["timeout"] < 60.0


def test_query_timeout_is_configurable(fake, monkeypatch):
    monkeypatch.setenv("EMBEDDING_QUERY_TIMEOUT_SECONDS", "3")
    monkeypatch.setenv("EMBEDDING_API_KEY", "test-key")

    captured = {}

    class _Client:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("openai.OpenAI", _Client)
    emb._openai_query_client = None
    emb.get_openai_client(query=True)

    assert captured["timeout"] == 3.0
