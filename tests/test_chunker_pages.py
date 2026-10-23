from softwiki.rag.chunker import build_document_chunks


def test_page_numbers_from_markers():
    text = ("A" * 800) + "\n\n--- Page Break ---\n\n" + ("B" * 800)
    chunks = build_document_chunks(
        1, text, {"title": "T", "source_name": "S"}, chunk_size=500, chunk_overlap=50
    )
    assert chunks
    assert any(c["page_start"] == 1 for c in chunks)
    assert any(c["page_end"] == 2 for c in chunks)
    assert all("--- Page Break ---" not in c["text"] for c in chunks)


def test_no_marker_means_unknown_pages():
    chunks = build_document_chunks(1, "plain text", {"title": "T", "source_name": "S"})
    assert chunks[0]["page_start"] is None
    assert chunks[0]["page_end"] is None
