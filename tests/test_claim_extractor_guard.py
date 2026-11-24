"""Claim extraction must survive malformed model output.

The model occasionally returns a claim object with no ``text`` (or a non-string).
``claims.text`` is NOT NULL, so one bad entry used to abort the whole document
and lose every claim in it (observed on ai-history doc 142).
"""
from datetime import datetime

import pytest

from softwiki.extraction import claim_extractor as module


class _Message:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Message(content)


class _Response:
    def __init__(self, content):
        self.choices = [_Choice(content)]


@pytest.fixture
def fake_llm(monkeypatch):
    """Make the extractor see a working client and a canned JSON answer."""
    payload = {
        "claims": [
            {"text": "Espresso uses 9 bar.", "actor": "SCA", "topic": "brewing"},
            {"text": None, "actor": "SCA", "topic": "brewing"},
            {"actor": "SCA", "topic": "brewing"},
            {"text": "   ", "actor": "SCA", "topic": "brewing"},
            {"text": 42, "actor": "SCA", "topic": "brewing"},
        ]
    }

    monkeypatch.setattr(
        module,
        "create_chat_completion",
        lambda *a, **kw: _Response(__import__("json").dumps(payload)),
        raising=False,
    )

    import softwiki.intelligence.llm_client as llm_client

    monkeypatch.setattr(
        llm_client,
        "create_chat_completion",
        lambda *a, **kw: _Response(__import__("json").dumps(payload)),
    )
    monkeypatch.setattr(
        llm_client,
        "get_llm_client_and_params",
        lambda profile: (object(), "test-model", 0.1, None),
    )


def test_claims_without_text_are_dropped_not_inserted(fake_llm):
    extractor = module.ClaimExtractor()
    claims = extractor.extract_claims(142, "some text", datetime(2026, 10, 4))

    assert len(claims) == 1
    assert claims[0].text == "Espresso uses 9 bar."
    # Every surviving claim is insertable (the failure mode was text=None).
    assert all(isinstance(c.text, str) and c.text for c in claims)


def test_ids_are_stable_for_the_same_claim(fake_llm):
    extractor = module.ClaimExtractor()
    first = extractor.extract_claims(142, "some text", datetime(2026, 10, 4))
    again = extractor.extract_claims(142, "some text", datetime(2026, 10, 4))
    assert [c.id for c in first] == [c.id for c in again]
