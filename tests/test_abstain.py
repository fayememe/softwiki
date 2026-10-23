from softwiki.source_store.db import init_tables, SessionLocal
from softwiki.intelligence.answer_engine import AnswerEngine


def test_empty_workspace_abstains(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path / "empty"))
    init_tables()
    db = SessionLocal()
    try:
        answer = AnswerEngine().ask(db, "What is the capital of France?")
        assert "don't have information" in answer.lower()
    finally:
        db.close()
