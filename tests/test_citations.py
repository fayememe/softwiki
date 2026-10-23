from softwiki.rag.citations import CitationManager


def test_page_citation_format_and_dedup():
    manager = CitationManager()
    first = manager.get_citation_num(
        1, {"title": "T", "source_name": "S", "page_start": 3, "page_end": 3}
    )
    second = manager.get_citation_num(
        1, {"title": "T", "source_name": "S", "page_start": 4, "page_end": 5}
    )
    again = manager.get_citation_num(
        1, {"title": "T", "source_name": "S", "page_start": 3, "page_end": 3}
    )
    assert first == again
    assert first != second
    rendered = manager.render_citations()
    assert "p.3" in rendered
    assert "pp.4-5" in rendered
