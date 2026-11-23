"""Propose → approve → execute.

The split matters: the agent can create a plan but only a human (wiki.apply)
can approve it, and approval performs the work.
"""

import json
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from softwiki.source_store.models import Base
from softwiki.wiki import plans


@pytest.fixture()
def db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path}/plans.db")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("WORKSPACES_ROOT", str(tmp_path))
    os.makedirs(os.path.join(tmp_path, "exports", "wiki", "pages"), exist_ok=True)
    os.makedirs(os.path.join(tmp_path, "config"), exist_ok=True)
    yield session
    session.close()


def _index(tmp_path, subjects):
    path = os.path.join(tmp_path, "exports", "wiki", "pages", "index.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"subjects": [
            {"subject": s, "slug": s.lower(), "claims_total": 10, "pages": [s.lower()]}
            for s in subjects
        ]}, f)
    for s in subjects:
        open(os.path.join(tmp_path, "exports", "wiki", "pages", f"{s.lower()}.md"), "w").close()


def test_unknown_kind_rejected(db):
    with pytest.raises(ValueError):
        plans.create_plan(db, "drop_tables", {"subjects": ["x"]})


def test_plan_starts_pending(db):
    plan = plans.create_plan(db, "delete_pages", {"subjects": ["Alpha"]}, proposed_by="wiki-work")
    assert plan.status == "pending"
    assert plans.list_plans(db, status="pending")[0].id == plan.id


def test_reject_does_not_touch_files(db, tmp_path):
    _index(tmp_path, ["Alpha"])
    plan = plans.create_plan(db, "delete_pages", {"subjects": ["Alpha"]})

    result = plans.decide(db, plan, False, decided_by="wiki-manage", reason="not now")
    assert result["status"] == "rejected"
    assert os.path.exists(os.path.join(tmp_path, "exports", "wiki", "pages", "alpha.md"))


def test_approve_executes_deletion(db, tmp_path):
    _index(tmp_path, ["Alpha", "Beta"])
    plan = plans.create_plan(db, "delete_pages", {"subjects": ["Alpha"]})

    result = plans.decide(db, plan, True, decided_by="wiki-manage")
    assert result["status"] == "applied"
    assert result["removed"] == ["Alpha"]

    pages = os.path.join(tmp_path, "exports", "wiki", "pages")
    assert not os.path.exists(os.path.join(pages, "alpha.md"))
    assert os.path.exists(os.path.join(pages, "beta.md"))
    index = json.load(open(os.path.join(pages, "index.json"), encoding="utf-8"))
    assert [e["subject"] for e in index["subjects"]] == ["Beta"]


def test_ignore_plan_also_records_the_rule(db, tmp_path):
    from softwiki.wiki import subject_rules

    _index(tmp_path, ["ROM"])
    plan = plans.create_plan(db, "ignore_subjects", {"subjects": ["ROM"]})
    plans.decide(db, plan, True, decided_by="wiki-manage")
    assert "ROM" in subject_rules.ignored()


def test_cannot_decide_twice(db):
    plan = plans.create_plan(db, "delete_pages", {"subjects": ["Alpha"]})
    plans.decide(db, plan, False, decided_by="wiki-manage")
    with pytest.raises(ValueError, match="already"):
        plans.decide(db, plan, True, decided_by="wiki-manage")
