"""Per-kb subject rules: ignore (no page) and lock (do not overwrite)."""

import os

import pytest

from softwiki.wiki import subject_rules


@pytest.fixture(autouse=True)
def _ws(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("WORKSPACES_ROOT", str(tmp_path))
    os.makedirs(os.path.join(tmp_path, "config"), exist_ok=True)
    yield


def test_defaults_are_empty():
    assert subject_rules.load() == {"ignore": [], "locked": []}


def test_add_and_remove_ignore():
    subject_rules.add_ignore("Arm")
    subject_rules.add_ignore("ARM Limited")
    assert subject_rules.ignored() == {"Arm", "ARM Limited"}

    subject_rules.remove_ignore("Arm")
    assert subject_rules.ignored() == {"ARM Limited"}


def test_ignore_is_idempotent():
    subject_rules.add_ignore("Arm")
    subject_rules.add_ignore("Arm")
    assert subject_rules.load()["ignore"] == ["Arm"]


def test_lock_and_unlock():
    subject_rules.set_locked("Cortex-M55", True)
    assert subject_rules.locked() == {"Cortex-M55"}
    subject_rules.set_locked("Cortex-M55", False)
    assert subject_rules.locked() == set()


def test_file_is_yaml_and_sorted():
    subject_rules.add_ignore("Zeta")
    subject_rules.add_ignore("Alpha")
    text = open(subject_rules._path(), encoding="utf-8").read()
    assert "ignore:" in text
    assert text.index("Alpha") < text.index("Zeta")


def test_corrupt_file_does_not_raise(tmp_path):
    path = subject_rules._path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("ignore: [unclosed\n")
    assert subject_rules.load() == {"ignore": [], "locked": []}


def test_ignored_subject_cannot_be_generated(tmp_path):
    """Generation refuses a subject the operator excluded."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from softwiki.source_store.models import Base, CanonicalClaim
    from softwiki.wiki.subject_pages import generate_subject_pages

    engine = create_engine(f"sqlite:///{tmp_path}/rules.db")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    subject_rules.add_ignore("Arm")
    with pytest.raises(ValueError, match="ignore"):
        generate_subject_pages(db, "Arm")
    db.close()
