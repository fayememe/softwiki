"""SOFTWIKI_DISABLE_LIGHTRAG must gate ingestion, not only queries."""

import pytest


@pytest.fixture(autouse=True)
def reset_adapter(monkeypatch):
    import softwiki.extraction.processor as processor

    monkeypatch.setattr(processor, "_lightrag_adapter", None)
    monkeypatch.setattr(processor, "_lightrag_adapter_warned", False)


def test_disable_flag_short_circuits_adapter(monkeypatch):
    import softwiki.extraction.processor as processor

    monkeypatch.setenv("SOFTWIKI_DISABLE_LIGHTRAG", "1")
    called = {"n": 0}

    class Boom:
        @classmethod
        def get_instance(cls):
            called["n"] += 1
            raise AssertionError("adapter must not be constructed when disabled")

    import softwiki.graph_rag.adapter as adapter_mod

    monkeypatch.setattr(adapter_mod, "LightRAGAdapter", Boom)
    monkeypatch.setattr(adapter_mod, "has_lightrag_credentials", lambda: True)

    assert processor._get_lightrag_adapter() is None
    assert called["n"] == 0


def test_adapter_used_when_flag_unset(monkeypatch):
    import softwiki.extraction.processor as processor
    import softwiki.graph_rag.adapter as adapter_mod

    monkeypatch.delenv("SOFTWIKI_DISABLE_LIGHTRAG", raising=False)
    sentinel = object()

    class Fake:
        @classmethod
        def get_instance(cls):
            return sentinel

    monkeypatch.setattr(adapter_mod, "LightRAGAdapter", Fake)
    monkeypatch.setattr(adapter_mod, "has_lightrag_credentials", lambda: True)

    assert processor._get_lightrag_adapter() is sentinel
