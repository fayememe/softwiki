"""Vector backend selection (file vs pgvector)."""

import os


def test_default_backend_is_file(monkeypatch):
    monkeypatch.delenv("SOFTWIKI_VECTOR_BACKEND", raising=False)
    from softwiki.rag.vector_store import FileVectorStore, LocalVectorStore

    store = LocalVectorStore()
    assert isinstance(store, FileVectorStore)
    assert store.get_current_path().endswith("vector_index.npz")


def test_pg_backend_is_selected_by_env(monkeypatch):
    monkeypatch.setenv("SOFTWIKI_VECTOR_BACKEND", "pg")
    from softwiki.rag.vector_store import LocalVectorStore, PgVectorStore

    store = LocalVectorStore()
    assert isinstance(store, PgVectorStore)
    assert store.get_current_path().startswith("pgvector://")
