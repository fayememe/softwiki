import os
import pytest
import shutil
import json
from datetime import datetime
from fastapi.testclient import TestClient
from softwiki.api.server import app
from softwiki.wiki.page_generator import WikiPageGenerator
from softwiki.source_store.db import SessionLocal, init_tables
from softwiki.source_store.models import Document, Claim
from softwiki.source_store.document_repo import DocumentRepository
from softwiki.intelligence.answer_engine import AnswerEngine

def test_user_mode_output_routing():
    os.environ["SOFTWIKI_MODE"] = "wiki-work"
    os.environ["SOFTWIKI_SESSION_ID"] = "test-session-123"
    
    try:
        generator = WikiPageGenerator()
        out_dir = generator.get_output_dir()
        
        # Verify that output path is routed to output/test-session-123
        assert "output" in out_dir
        assert "test-session-123" in out_dir
        assert os.path.isdir(out_dir)
        
    finally:
        # Clean up
        if "SOFTWIKI_MODE" in os.environ:
            del os.environ["SOFTWIKI_MODE"]
        if "SOFTWIKI_SESSION_ID" in os.environ:
            del os.environ["SOFTWIKI_SESSION_ID"]

def test_user_mode_write_restrictions():
    client = TestClient(app)
    
    # 1. Test study mode restrictions
    os.environ["SOFTWIKI_MODE"] = "wiki-study"
    try:
        response = client.post("/api/ingest/url", json={"url": "https://example.com", "source_id": "test"})
        assert response.status_code == 403
        assert "disabled in study/work modes" in response.json()["detail"]
        
        import io
        dummy_file = io.BytesIO(b"dummy pdf content")
        response = client.post("/api/ingest/file", files={"file": ("dummy.pdf", dummy_file, "application/pdf")})
        assert response.status_code == 403
        assert "disabled in study/work modes" in response.json()["detail"]
        
        response = client.post("/api/index")
        assert response.status_code == 403
        assert "disabled in study/work modes" in response.json()["detail"]
        
        response = client.delete("/api/documents/123")
        assert response.status_code == 403
        assert "disabled in study/work modes" in response.json()["detail"]

        response = client.post("/api/wiki/build", json={"topic": "test-topic"})
        assert response.status_code == 403
        assert "disabled in study mode" in response.json()["detail"]
        
    finally:
        if "SOFTWIKI_MODE" in os.environ:
            del os.environ["SOFTWIKI_MODE"]

    # 2. Test work mode restrictions (allows wiki building, blocks others)
    os.environ["SOFTWIKI_MODE"] = "wiki-work"
    try:
        response = client.post("/api/ingest/url", json={"url": "https://example.com", "source_id": "test"})
        assert response.status_code == 403
        assert "disabled in study/work modes" in response.json()["detail"]
        
        response = client.post("/api/index")
        assert response.status_code == 403
        assert "disabled in study/work modes" in response.json()["detail"]
        
    finally:
        if "SOFTWIKI_MODE" in os.environ:
            del os.environ["SOFTWIKI_MODE"]

def test_user_mode_wiki_generation_files():
    ws = "data/test_user_mode_ws"
    if os.path.exists(ws):
        shutil.rmtree(ws)
        
    os.environ["WORKSPACE_DIR"] = ws
    os.environ["SOFTWIKI_MODE"] = "wiki-work"
    os.environ["SOFTWIKI_SESSION_ID"] = "session-wiki-test"
    
    try:
        init_tables()
        db = SessionLocal()
        
        # Create a document
        doc = Document(
            title="Sino-Soviet Relations",
            raw_text="The relationship between China and Soviet Union was complex.",
            cleaned_text="The relationship between China and Soviet Union was complex.",
            hash="h1",
            published_at=datetime.utcnow()
        )
        doc = DocumentRepository.create_document(db, doc)
        
        # Create a claim
        claim = Claim(
            id="claim1",
            document_id=doc.id,
            actor="china",
            stance="supportive",
            confidence=0.9,
            text="China seeks border stability.",
            topic="border-negotiations",
            published_at=datetime.utcnow()
        )
        db.add(claim)
        db.commit()
        
        generator = WikiPageGenerator()
        filepath = generator.generate_topic_page(db, "border-negotiations")
        
        assert os.path.exists(filepath)
        assert filepath.endswith(".md")
        
        # Verify JSON also generated
        json_filepath = filepath.replace(".md", ".json")
        assert os.path.exists(json_filepath)
        
        # Read and check JSON content
        with open(json_filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        assert data["topic_id"] == "border-negotiations"
        assert data["summary"] is not None
        assert len(data["claims"]) == 1
        assert data["claims"][0]["actor"] == "china"
        assert data["claims"][0]["stance"] == "supportive"
        
    finally:
        # Clean up
        db.close()
        if os.path.exists(ws):
            shutil.rmtree(ws)
        # Clean up output dir
        out_dir = os.path.abspath(os.path.join("output", "session-wiki-test"))
        if os.path.exists(out_dir):
            shutil.rmtree(out_dir)
            
        for env_var in ["WORKSPACE_DIR", "SOFTWIKI_MODE", "SOFTWIKI_SESSION_ID"]:
            if env_var in os.environ:
                del os.environ[env_var]

def test_user_mode_ask_generation_files():
    ws = "data/test_user_mode_ws_ask"
    if os.path.exists(ws):
        shutil.rmtree(ws)
        
    os.environ["WORKSPACE_DIR"] = ws
    os.environ["SOFTWIKI_MODE"] = "wiki-work"
    os.environ["SOFTWIKI_SESSION_ID"] = "session-ask-test"
    # Ensure offline mode generates answer
    os.environ["OPENAI_API_KEY"] = "your_openai_api_key_placeholder"
    
    try:
        init_tables()
        db = SessionLocal()
        
        # Create a document
        doc = Document(
            title="Sino-Soviet Relations",
            raw_text="The relationship between China and Soviet Union was complex.",
            cleaned_text="The relationship between China and Soviet Union was complex.",
            hash="h1",
            published_at=datetime.utcnow()
        )
        doc = DocumentRepository.create_document(db, doc)
        
        # Create a claim to provide query context in ClaimDB
        claim = Claim(
            id="claim2",
            document_id=doc.id,
            actor="soviet_union",
            stance="cautious",
            confidence=0.85,
            text="Sino-Soviet relations are historically complex.",
            topic="relations",
            published_at=datetime.utcnow()
        )
        db.add(claim)
        db.commit()
        
        engine = AnswerEngine()
        answer = engine.ask(db, "How were Sino-Soviet relations?")
        
        # Verify output files exist
        out_dir = os.path.abspath(os.path.join("output", "session-ask-test"))
        assert os.path.isdir(out_dir)
        
        # Look for ask files in output folder
        files = os.listdir(out_dir)
        md_files = [f for f in files if f.startswith("ask_") and f.endswith(".md")]
        json_files = [f for f in files if f.startswith("ask_") and f.endswith(".json")]
        
        assert len(md_files) == 1
        assert len(json_files) == 1
        
        # Read JSON file
        with open(os.path.join(out_dir, json_files[0]), "r", encoding="utf-8") as f:
            data = json.load(f)
            
        assert "sino_soviet" in json_files[0]
        assert data["question"] == "How were Sino-Soviet relations?"
        assert data["session_id"] == "session-ask-test"
        assert data["answer"] == answer
        
    finally:
        # Clean up
        db.close()
        if os.path.exists(ws):
            shutil.rmtree(ws)
        out_dir = os.path.abspath(os.path.join("output", "session-ask-test"))
        if os.path.exists(out_dir):
            shutil.rmtree(out_dir)
            
        for env_var in ["WORKSPACE_DIR", "SOFTWIKI_MODE", "SOFTWIKI_SESSION_ID", "OPENAI_API_KEY"]:
            if env_var in os.environ:
                del os.environ[env_var]

def test_user_mode_random_session_id_generation():
    os.environ["SOFTWIKI_MODE"] = "wiki-work"
    if "SOFTWIKI_SESSION_ID" in os.environ:
        del os.environ["SOFTWIKI_SESSION_ID"]
        
    try:
        from softwiki.config import get_session_id
        session_id = get_session_id()
        
        # Verify it starts with 'session-' and is followed by 8 characters
        assert session_id.startswith("session-")
        rand_part = session_id[len("session-"):]
        assert len(rand_part) == 8
        assert rand_part.isalnum()
        
        # Verify it is persistent for the process once generated
        assert get_session_id() == session_id
        
    finally:
        for env_var in ["SOFTWIKI_MODE", "SOFTWIKI_SESSION_ID"]:
            if env_var in os.environ:
                del os.environ[env_var]

