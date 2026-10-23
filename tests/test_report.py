import json
import os

from softwiki.intelligence.report import generate_report, load_template
from softwiki.source_store.db import init_tables, SessionLocal


def test_load_template():
    template = load_template("research-report")
    assert template["id"] == "research-report"
    assert template["sections"]


def test_generate_report(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path / "ws"))
    init_tables()
    db = SessionLocal()
    try:
        result = generate_report(db, "What is a timer event?", "course-qa")
        assert os.path.exists(result["report_path"])
        assert os.path.exists(result["manifest_path"])
        with open(result["manifest_path"], encoding="utf-8") as f:
            manifest = json.load(f)
        assert manifest["template"] == "course-qa"
        assert manifest["question"] == "What is a timer event?"
    finally:
        db.close()
