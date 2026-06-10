import os
import shutil
from datetime import datetime
from softwiki.source_store.db import SessionLocal, init_tables
from softwiki.source_store.models import Document
from softwiki.source_store.document_repo import DocumentRepository

def test_workspace_database_isolation():
    ws1 = "data/test_ws1"
    ws2 = "data/test_ws2"
    
    # Clean up old dirs if left over
    for ws in [ws1, ws2]:
        if os.path.exists(ws):
            shutil.rmtree(ws)
            
    try:
        # 1. Initialize Workspace 1
        os.environ["WORKSPACE_DIR"] = ws1
        init_tables()
        db1 = SessionLocal()
        
        doc1 = Document(
            title="Workspace One Document",
            raw_text="Workspace 1 content",
            cleaned_text="Workspace 1 content",
            hash="hash1",
            published_at=datetime.utcnow()
        )
        DocumentRepository.create_document(db1, doc1)
        
        # Verify document exists in WS1
        docs_ws1 = DocumentRepository.get_all_documents(db1)
        assert len(docs_ws1) == 1
        assert docs_ws1[0].title == "Workspace One Document"
        db1.close()

        # 2. Switch to Workspace 2
        os.environ["WORKSPACE_DIR"] = ws2
        init_tables()
        db2 = SessionLocal()
        
        # Verify Workspace 2 database is completely empty
        docs_ws2 = DocumentRepository.get_all_documents(db2)
        assert len(docs_ws2) == 0
        
        # Add a different document in Workspace 2
        doc2 = Document(
            title="Workspace Two Document",
            raw_text="Workspace 2 content",
            cleaned_text="Workspace 2 content",
            hash="hash2",
            published_at=datetime.utcnow()
        )
        DocumentRepository.create_document(db2, doc2)
        
        docs_ws2_updated = DocumentRepository.get_all_documents(db2)
        assert len(docs_ws2_updated) == 1
        assert docs_ws2_updated[0].title == "Workspace Two Document"
        db2.close()

        # 3. Switch back to Workspace 1 and verify data is still there intact
        os.environ["WORKSPACE_DIR"] = ws1
        db1_reopen = SessionLocal()
        docs_ws1_final = DocumentRepository.get_all_documents(db1_reopen)
        assert len(docs_ws1_final) == 1
        assert docs_ws1_final[0].title == "Workspace One Document"
        db1_reopen.close()

    finally:
        from softwiki.source_store.db import get_engine
        try:
            get_engine().dispose()
        except Exception:
            pass
        # Cleanup
        for ws in [ws1, ws2]:
            if os.path.exists(ws):
                try:
                    shutil.rmtree(ws)
                except Exception:
                    pass
        if "WORKSPACE_DIR" in os.environ:
            del os.environ["WORKSPACE_DIR"]

def test_opencode_config_generation():
    import json
    from unittest.mock import patch
    ws = "data/test_opencode_config_ws"
    if os.path.exists(ws):
        shutil.rmtree(ws)
    os.makedirs(ws, exist_ok=True)
    os.environ["WORKSPACE_DIR"] = ws
    os.environ["SOFTWIKI_MODE"] = "wiki-study"

    try:
        from softwiki.cli.shell import start_shell, get_workspace_runtime_dir
        abs_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        runtime_dir = get_workspace_runtime_dir(ws, abs_project_root)

        with patch("os.execvp") as mock_execvp, patch("softwiki.cli.shell._print_banner"), patch("time.sleep"):
            start_shell()
            
            # Verify opencode.json was generated inside the project-level runtime directory
            config_path = os.path.join(runtime_dir, "opencode", "opencode.json")
            assert os.path.exists(config_path)
            
            with open(config_path, "r") as f:
                config = json.load(f)
                
            assert config["$schema"] == "https://opencode.ai/config.json"
            assert "gemini-compat/gemini-2.5-flash" in config["model"]
            assert "agent" in config
            assert "wiki-study" in config["agent"]
            assert config["agent"]["wiki-study"]["mode"] == "primary"
            assert "sisyphus" in config["agent"]
            assert config["agent"]["sisyphus"]["disable"] is True
            assert config["agent"]["build"]["disable"] is True
            assert config["agent"]["plan"]["disable"] is True
            assert config["agent"]["oracle"]["disable"] is True
            
            # Verify MCP server is configured locally
            assert "mcp" in config
            assert "softwiki" in config["mcp"]
            
    finally:
        from softwiki.source_store.db import get_engine
        try:
            get_engine().dispose()
        except Exception:
            pass
        if os.path.exists(ws):
            try:
                shutil.rmtree(ws)
            except Exception:
                pass
        abs_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        runtime_parent = os.path.join(abs_project_root, ".softwiki_runtime")
        import glob
        for fpath in glob.glob(os.path.join(runtime_parent, "test_opencode_config_ws_*")):
            if os.path.exists(fpath):
                try:
                    shutil.rmtree(fpath)
                except Exception:
                    pass
        for env_var in ["WORKSPACE_DIR", "SOFTWIKI_MODE"]:
            if env_var in os.environ:
                del os.environ[env_var]

def test_dynamic_topics_discovery():
    from fastapi.testclient import TestClient
    from softwiki.api.server import app
    from softwiki.source_store.models import Claim
    
    ws = "data/test_dynamic_topics_ws"
    if os.path.exists(ws):
        shutil.rmtree(ws)
    os.makedirs(ws, exist_ok=True)
    os.environ["WORKSPACE_DIR"] = ws
    
    try:
        init_tables()
        db = SessionLocal()
        
        # Insert a sample claim under a custom topic
        claim1 = Claim(
            id="claim_test_1",
            document_id=1,
            text="Claim detail",
            actor="TestActor",
            topic="low-altitude-economy",
            stance="supportive",
            confidence=0.85,
            published_at=datetime.utcnow()
        )
        db.add(claim1)
        db.commit()
        db.close()
        
        # Test the REST API endpoint /api/wiki/topics
        client = TestClient(app)
        response = client.get("/api/wiki/topics")
        assert response.status_code == 200
        
        data = response.json()
        assert "topics" in data
        assert "low-altitude-economy" in data["topics"]
        assert data["topics"]["low-altitude-economy"]["aliases"] == ["low-altitude-economy"]
        
    finally:
        from softwiki.source_store.db import get_engine
        try:
            get_engine().dispose()
        except Exception:
            pass
        if os.path.exists(ws):
            try:
                shutil.rmtree(ws)
            except Exception:
                pass
        if "WORKSPACE_DIR" in os.environ:
            del os.environ["WORKSPACE_DIR"]
