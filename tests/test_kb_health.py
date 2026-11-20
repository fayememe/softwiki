"""Tests for knowledge-base availability probing.

`/api/kb` lists kbs from disk (design D1: no DB access). That is correct for
agents but wrong for the UI, which must not offer a kb whose database was never
created in this instance — switching to it would answer 500.
"""

import os

import pytest

from softwiki.kb.health import invalidate, probe_kb


@pytest.fixture(autouse=True)
def _clear_cache():
    invalidate()
    yield
    invalidate()


def _make_kb(root, name, *, with_db=True):
    path = os.path.join(root, name)
    os.makedirs(os.path.join(path, ".softwiki", "index"), exist_ok=True)
    os.makedirs(os.path.join(path, "config"), exist_ok=True)
    if with_db:
        # SQLite fallback: the probe looks for this file.
        os.makedirs(os.path.join(path, ".softwiki"), exist_ok=True)
        with open(os.path.join(path, ".softwiki", "processed.db"), "wb"):
            pass
    return path


def test_probe_true_for_sqlite_database(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL_TEMPLATE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    path = _make_kb(str(tmp_path), "good")
    available, reason = probe_kb(path, use_cache=False)
    assert available is True
    assert reason is None


def test_probe_false_when_database_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL_TEMPLATE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    path = _make_kb(str(tmp_path), "nodb", with_db=False)
    available, reason = probe_kb(path, use_cache=False)
    assert available is False
    assert reason


def test_probe_false_for_unknown_postgres_database(tmp_path, monkeypatch):
    """A directory can exist while its database was never created (the real
    trial-host case: two compose stacks, one workspace root)."""
    monkeypatch.setenv(
        "DATABASE_URL_TEMPLATE",
        "postgresql+psycopg2://u:p@127.0.0.1:1/softwiki_{workspace}",
    )
    monkeypatch.setenv("SOFTWIKI_KB_PROBE_TIMEOUT", "1")
    path = _make_kb(str(tmp_path), "ghost")
    available, reason = probe_kb(path, use_cache=False)
    assert available is False
    assert reason


def test_probe_is_cached(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL_TEMPLATE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    path = _make_kb(str(tmp_path), "cached")

    first = probe_kb(path)
    assert first[0] is True

    # Removing the database must not change the answer within the TTL.
    os.remove(os.path.join(path, ".softwiki", "processed.db"))
    assert probe_kb(path)[0] is True

    invalidate(path)
    assert probe_kb(path)[0] is False


def test_probe_reports_bad_template_without_raising(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL_TEMPLATE", "not-a-url-{workspace}")
    path = _make_kb(str(tmp_path), "bad")
    available, reason = probe_kb(path, use_cache=False)
    assert available is False
    assert reason
