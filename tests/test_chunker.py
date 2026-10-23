from softwiki.rag.chunker import chunk_text


def test_long_ascii_paragraph_is_bounded():
    chunks = chunk_text("A" * 60000, chunk_size=1000, chunk_overlap=200)
    assert chunks
    assert max(len(c["text"]) for c in chunks) <= 1000


def test_long_cjk_paragraph_is_bounded():
    chunks = chunk_text("中文" * 20000, chunk_size=1000, chunk_overlap=200)
    assert chunks
    assert max(len(c["text"]) for c in chunks) <= 1000


def test_many_sentences_respect_size():
    chunks = chunk_text("Hello world. " * 10000, chunk_size=1000, chunk_overlap=200)
    assert chunks
    assert max(len(c["text"]) for c in chunks) <= 1000
