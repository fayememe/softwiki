from types import SimpleNamespace

from softwiki.api.server import _build_sources


def test_build_sources_matches_citations():
    document = SimpleNamespace(id=1)
    chunk = SimpleNamespace(text="evidence", page_start=5, page_end=7)
    engine = SimpleNamespace(
        last_search_results=[
            {"document": document, "chunk": chunk, "score": 0.03}
        ],
        last_citations=[
            {
                "num": 1,
                "doc_id": 1,
                "page_start": 5,
                "page_end": 7,
                "title": "T",
                "url": None,
                "source_name": "S",
                "published_at": "2026-01-01",
            },
            {
                "num": 2,
                "doc_id": 2,
                "page_start": None,
                "page_end": None,
                "title": "U",
                "url": None,
                "source_name": "S",
                "published_at": None,
            },
        ],
    )

    sources = _build_sources(engine)
    assert sources[0]["citation_num"] == 1
    assert sources[0]["text"] == "evidence"
    assert sources[0]["score"] == 0.03
    assert sources[1]["citation_num"] == 2
    assert sources[1]["score"] == 0.0
    assert sources[1]["published_at"] == "Unknown"
