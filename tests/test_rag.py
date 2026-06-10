import os
import shutil
import numpy as np
from softwiki.rag.chunker import chunk_text, build_document_chunks
from softwiki.rag.vector_store import LocalVectorStore
from softwiki.rag.bm25_store import Bm25Store, tokenize

def test_chunk_text():
    text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
    chunks = chunk_text(text, chunk_size=50, chunk_overlap=10)
    assert len(chunks) > 0
    for c in chunks:
        assert "text" in c
        assert "section" in c

def test_build_document_chunks():
    text = "Project Alpha news.\n\nMore details on new features."
    metadata = {
        "title": "Project Alpha Release 2024",
        "source_name": "Reuters",
        "published_at": "2024-10-23"
    }
    chunks = build_document_chunks(doc_id=1, text=text, metadata=metadata, chunk_size=100)
    assert len(chunks) > 0
    first_chunk = chunks[0]
    assert first_chunk["document_id"] == 1
    assert "Project Alpha Release 2024" in first_chunk["text"]
    assert "Reuters" in first_chunk["text"]

def test_local_vector_store():
    # Make sure we clean/isolate the test index path
    os.environ["WORKSPACE_DIR"] = "data/test_workspace"
    store = LocalVectorStore()
    
    vec1 = [1.0, 0.0, 0.0]
    vec2 = [0.0, 1.0, 0.0]
    
    store.add_vectors([101, 102], [vec1, vec2])
    
    results = store.search([1.0, 0.1, 0.0], top_k=2)
    assert len(results) == 2
    assert results[0]["chunk_id"] == 101
    assert results[0]["score"] > 0.9
    
    # Cleanup
    current_path = store.get_current_path()
    if os.path.exists(current_path):
        os.remove(current_path)

def test_bm25_store():
    os.environ["WORKSPACE_DIR"] = "data/test_workspace"
    store = Bm25Store()
    
    corpus = {
        1: "Server and client discuss common communication protocol",
        2: "Data pipeline imports record volume of logs from server A",
        3: "Subsystem decoupling efforts accelerate among core module developers"
    }
    
    store.rebuild_index(corpus)
    
    results = store.search("subsystem decoupling", top_k=2)
    assert len(results) > 0
    assert results[0]["chunk_id"] == 3
    
    # Cleanup
    current_path = store.get_current_path()
    if os.path.exists(current_path):
        os.remove(current_path)

def test_tokenize():
    tokens = tokenize("ProjectAlpha 模块解耦 and local module integration.")
    assert "projectalpha" in tokens
    assert "and" in tokens
    assert "模" in tokens
    assert "块" in tokens
    assert "解" in tokens
    assert "耦" in tokens
