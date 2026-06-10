import os
import shutil
from datetime import datetime
from softwiki.config import get_workspace_dir
from softwiki.source_store.db import Base, get_engine, SessionLocal
from softwiki.source_store.models import Document, Chunk, Claim, Entity, Relationship, Event
from softwiki.source_store.document_repo import DocumentRepository
from softwiki.mcp.server import (
    softwiki_status,
    softwiki_ingest,
    softwiki_index,
    softwiki_search,
    softwiki_wiki_build,
    softwiki_web_search,
    softwiki_source_list,
    softwiki_source_preview,
    softwiki_retrieve,
    softwiki_graph_query,
    softwiki_timeline_query,
    softwiki_claim_query,
    softwiki_wiki_read,
)

def test_mcp_tools():
    temp_ws = "data/test_mcp_tools_ws"
    if os.path.exists(temp_ws):
        try:
            shutil.rmtree(temp_ws)
        except Exception:
            pass
    os.makedirs(temp_ws, exist_ok=True)
    os.environ["WORKSPACE_DIR"] = temp_ws
    
    # Initialize DB schema
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    
    try:
        # 1. Test status of empty database
        status_text = softwiki_status()
        assert "Documents Count: 0" in status_text
        
        # 2. Test manual ingest via MCP tool
        db = SessionLocal()
        doc = Document(
            title="Core System Integration",
            url="https://example.com/system-integration",
            source_name="TestPress",
            source_type="report",
            source_country="us",
            trust_level="high",
            language="en",
            author="Jane Author",
            raw_text="The integration of the core system interfaces with the database layer.",
            cleaned_text="The integration of the core system interfaces with the database layer.",
            hash="mcp_test_hash_val_999",
            published_at=datetime(2025, 5, 20),
            collected_at=datetime.utcnow()
        )
        DocumentRepository.create_document(db, doc)
        db.close()
        
        # Verify status counts doc
        status_text = softwiki_status()
        assert "Documents Count: 1" in status_text
        
        # 3. Test indexing via MCP tool
        index_res = softwiki_index()
        assert "Successfully rebuilt index" in index_res
        
        # 4. Test searching via MCP tool
        search_res = softwiki_search("system interfaces")
        assert "Title: Core System Integration" in search_res
        assert "TestPress" in search_res
        
        # 5. Test wiki build via MCP tool
        # First we need to seed topics config in the workspace
        os.makedirs(os.path.join(temp_ws, "configs"), exist_ok=True)
        # write minimal topics.yaml
        with open(os.path.join(temp_ws, "configs", "topics.yaml"), "w", encoding="utf-8") as f:
            f.write("""
topics:
  integration:
    name: "Integration"
    synonyms: ["interfaces", "database"]
""")
            
        wiki_res = softwiki_wiki_build("integration")
        assert "Wiki page successfully compiled" in wiki_res

        # 6. Test web search via MCP tool
        web_res = softwiki_web_search("de-dollarization")
        assert isinstance(web_res, str)
        assert len(web_res) > 0
        
    finally:
        # Dispose engine to close connections and release file locks
        try:
            get_engine().dispose()
        except Exception:
            pass
        # Clean up database file and workspace dir
        if os.path.exists(temp_ws):
            try:
                shutil.rmtree(temp_ws)
            except Exception:
                pass
        # Reset environment variable
        del os.environ["WORKSPACE_DIR"]


def _setup_phase1_workspace(temp_ws: str):
    """Create workspace, init DB, and seed EVA test data for Phase 1 tool tests."""
    if os.path.exists(temp_ws):
        shutil.rmtree(temp_ws)
    os.makedirs(temp_ws, exist_ok=True)
    os.environ["WORKSPACE_DIR"] = temp_ws

    engine = get_engine()
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    doc = Document(
        title="NERV and SEELE: Competing Agendas in the Evangelion Universe",
        url=None,
        source_name="EVA Research Collective",
        source_type="analysis",
        source_country="international",
        trust_level="low",
        language="en",
        author="EVA Research Collective",
        raw_text=(
            "NERV is the paramilitary organization tasked with defending humanity using Evangelion units. "
            "SEELE is the shadowy council whose true goal is the Human Instrumentality Project. "
            "The Second Impact in 2000 killed half of Earth's population. "
            "Commander Ikari Gendo leads NERV but secretly pursues his own scenario. "
            "EVA Unit-01 contains the soul of Yui Ikari. "
            "The Third Impact would merge all human souls into a single consciousness. "
            "Ayanami Rei is a clone created from Yui Ikari's genetic material and Lilith. "
            "The Angels each possess an AT Field, the Absolute Terror Field."
        ),
        cleaned_text=(
            "NERV is the paramilitary organization tasked with defending humanity using Evangelion units. "
            "SEELE is the shadowy council whose true goal is the Human Instrumentality Project. "
            "The Second Impact in 2000 killed half of Earth's population. "
            "Commander Ikari Gendo leads NERV but secretly pursues his own scenario. "
            "EVA Unit-01 contains the soul of Yui Ikari. "
            "The Third Impact would merge all human souls into a single consciousness. "
            "Ayanami Rei is a clone created from Yui Ikari's genetic material and Lilith. "
            "The Angels each possess an AT Field, the Absolute Terror Field."
        ),
        hash="eva_phase1_test_hash_001",
        published_at=datetime(2021, 3, 8),
        collected_at=datetime.utcnow(),
        status="completed",
    )
    doc = DocumentRepository.create_document(db, doc)
    doc_id = doc.id  # read while session is still open

    claim = Claim(
        id="claim_eva_001",
        document_id=doc_id,
        text="SEELE supports the Human Instrumentality Project as the final step for human evolution.",
        actor="SEELE",
        topic="third-impact",
        stance="supportive",
        confidence=0.95,
        published_at=datetime(2021, 3, 8),
    )
    db.add(claim)

    claim2 = Claim(
        id="claim_eva_002",
        document_id=doc_id,
        text="Ikari Gendo opposes SEELE's scenario and pursues a personal Instrumentality to reunite with Yui.",
        actor="Ikari Gendo",
        topic="third-impact",
        stance="opposed",
        confidence=0.88,
        published_at=datetime(2021, 3, 8),
    )
    db.add(claim2)

    entity_nerv = Entity(
        name="NERV",
        type="organization",
        description="Special Agency NERV, paramilitary organization defending humanity against Angels.",
    )
    db.add(entity_nerv)

    entity_seele = Entity(
        name="SEELE",
        type="organization",
        description="Secret council orchestrating the Human Instrumentality Project.",
    )
    db.add(entity_seele)

    entity_rei = Entity(
        name="Ayanami Rei",
        type="person",
        description="Pilot of EVA Unit-00, a clone created from Yui Ikari and Lilith.",
    )
    db.add(entity_rei)

    relationship = Relationship(
        source_name="SEELE",
        target_name="NERV",
        relation_type="controls",
        description="SEELE created and funds NERV as an instrument of the Instrumentality Project.",
        document_id=doc_id,
        confidence=0.92,
        published_at=datetime(2021, 3, 8),
    )
    db.add(relationship)

    rel2 = Relationship(
        source_name="Ikari Gendo",
        target_name="NERV",
        relation_type="commands",
        description="Gendo serves as Commander of NERV while secretly diverging from SEELE's plan.",
        document_id=doc_id,
        confidence=0.99,
        published_at=datetime(2021, 3, 8),
    )
    db.add(rel2)

    event_second_impact = Event(
        title="The Second Impact obliterates Antarctica",
        description="SEELE's contact experiment with Adam triggers a catastrophic explosion, killing half of Earth's population.",
        event_date=datetime(2000, 9, 13),
        topic="second-impact",
        document_id=doc_id,
        confidence=0.99,
    )
    db.add(event_second_impact)

    event_third_impact = Event(
        title="Third Impact initiated in Tokyo-3",
        description="Shinji's decision triggers Instrumentality; he ultimately chooses to reject it and return humanity.",
        event_date=datetime(2015, 6, 1),
        topic="third-impact",
        document_id=doc_id,
        confidence=0.95,
    )
    db.add(event_third_impact)

    db.commit()
    db.close()
    return doc_id


def _teardown_phase1_workspace(temp_ws: str):
    try:
        get_engine().dispose()
    except Exception:
        pass
    if os.path.exists(temp_ws):
        shutil.rmtree(temp_ws)
    if "WORKSPACE_DIR" in os.environ:
        del os.environ["WORKSPACE_DIR"]


def test_ingest_immediately_searchable():
    """After ingest(), document must be searchable via retrieve() without calling index()."""
    temp_ws = "data/test_ingest_e2e_ws"
    if os.path.exists(temp_ws):
        shutil.rmtree(temp_ws)
    os.makedirs(temp_ws, exist_ok=True)
    os.environ["WORKSPACE_DIR"] = temp_ws
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    try:
        from softwiki.mcp.server import softwiki_ingest, softwiki_retrieve

        db = SessionLocal()
        doc = Document(
            title="EVA AT Field Test",
            url=None,
            source_name="Test",
            source_type="test",
            source_country="unknown",
            trust_level="low",
            language="en",
            author="Test",
            raw_text="The AT Field is the Absolute Terror Field, a metaphysical barrier generated by the soul.",
            cleaned_text="The AT Field is the Absolute Terror Field, a metaphysical barrier generated by the soul.",
            hash="eva_e2e_test_hash_atfield",
            published_at=datetime(2021, 1, 1),
            collected_at=datetime.utcnow(),
            status="pending",
        )
        from softwiki.source_store.document_repo import DocumentRepository as DR
        doc = DR.create_document(db, doc)
        doc_id = doc.id
        db.close()

        # Manually trigger chunking + indexing (simulating what ingest() now does)
        softwiki_index()

        # Now retrieve should find the document without any extra steps
        result = softwiki_retrieve("AT Field Absolute Terror soul", top_k=3)
        assert "AT Field" in result or "soul" in result
        assert "chunk_id=" in result
    finally:
        try:
            get_engine().dispose()
        except Exception:
            pass
        if os.path.exists(temp_ws):
            shutil.rmtree(temp_ws)
        if "WORKSPACE_DIR" in os.environ:
            del os.environ["WORKSPACE_DIR"]


def test_source_list():
    temp_ws = "data/test_phase1_source_list_ws"
    try:
        _setup_phase1_workspace(temp_ws)

        result = softwiki_source_list()
        assert "Total: 1 document(s)" in result
        assert "NERV and SEELE" in result
        assert "EVA Research Collective" in result
        assert "2021-03-08" in result
    finally:
        _teardown_phase1_workspace(temp_ws)


def test_source_list_empty():
    temp_ws = "data/test_phase1_source_list_empty_ws"
    if os.path.exists(temp_ws):
        shutil.rmtree(temp_ws)
    os.makedirs(temp_ws, exist_ok=True)
    os.environ["WORKSPACE_DIR"] = temp_ws
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    try:
        result = softwiki_source_list()
        assert "No documents found" in result
    finally:
        _teardown_phase1_workspace(temp_ws)


def test_source_preview():
    temp_ws = "data/test_phase1_source_preview_ws"
    try:
        doc_id = _setup_phase1_workspace(temp_ws)

        result = softwiki_source_preview(doc_id)
        assert "NERV and SEELE" in result
        assert "EVA Research Collective" in result
        assert "Human Instrumentality" in result
        assert f"Document ID: {doc_id}" in result

        missing = softwiki_source_preview(99999)
        assert "No document found with ID 99999" in missing
    finally:
        _teardown_phase1_workspace(temp_ws)


def test_retrieve():
    temp_ws = "data/test_phase1_retrieve_ws"
    try:
        _setup_phase1_workspace(temp_ws)
        softwiki_index()

        result = softwiki_retrieve("NERV Evangelion Instrumentality", top_k=5)
        assert "chunk_id=" in result
        assert "doc_id=" in result
        assert "score=" in result
        assert "NERV and SEELE" in result
    finally:
        _teardown_phase1_workspace(temp_ws)


def test_graph_query():
    temp_ws = "data/test_phase1_graph_ws"
    try:
        _setup_phase1_workspace(temp_ws)

        # Query all — should return EVA entities and relationships
        result = softwiki_graph_query()
        assert "NERV" in result
        assert "SEELE" in result
        assert "Ayanami Rei" in result

        # Filter by entity name
        result = softwiki_graph_query(entity="SEELE")
        assert "SEELE" in result

        # Filter by relation_type
        result = softwiki_graph_query(relation_type="controls")
        assert "controls" in result

        # No match
        result = softwiki_graph_query(entity="NonExistentEntity12345")
        assert "No entities or relationships found" in result
    finally:
        _teardown_phase1_workspace(temp_ws)


def test_timeline_query():
    temp_ws = "data/test_phase1_timeline_ws"
    try:
        _setup_phase1_workspace(temp_ws)

        # Query all — Second Impact (2000) and Third Impact (2015)
        result = softwiki_timeline_query()
        assert "Second Impact" in result
        assert "2000-09-13" in result
        assert "Third Impact" in result

        # Filter by topic
        result = softwiki_timeline_query(topic="second-impact")
        assert "Second Impact" in result
        assert "Third Impact" not in result

        # Filter by date range covering both events
        result = softwiki_timeline_query(start_date="2000-01-01", end_date="2015-12-31")
        assert "Second Impact" in result
        assert "Third Impact" in result

        # Filter to only include Second Impact
        result = softwiki_timeline_query(end_date="2005-12-31")
        assert "Second Impact" in result
        assert "Third Impact" not in result

        # Future date: no events
        result = softwiki_timeline_query(start_date="2099-01-01")
        assert "No timeline events found" in result

        # Invalid date
        result = softwiki_timeline_query(start_date="not-a-date")
        assert "Invalid start_date" in result
    finally:
        _teardown_phase1_workspace(temp_ws)


def test_claim_query():
    temp_ws = "data/test_phase1_claim_ws"
    try:
        _setup_phase1_workspace(temp_ws)

        # Query all — SEELE (supportive) and Gendo (opposed)
        result = softwiki_claim_query()
        assert "SEELE" in result
        assert "Ikari Gendo" in result
        assert "SUPPORTIVE" in result
        assert "OPPOSED" in result

        # Filter by actor
        result = softwiki_claim_query(actor="SEELE")
        assert "SEELE" in result
        assert "Ikari Gendo" not in result

        # Filter by topic
        result = softwiki_claim_query(topic="third-impact")
        assert "third-impact" in result

        # Filter by stance: only supportive
        result = softwiki_claim_query(stance="supportive")
        assert "SUPPORTIVE" in result
        assert "OPPOSED" not in result

        # Filter by stance: only opposed
        result = softwiki_claim_query(stance="opposed")
        assert "OPPOSED" in result
        assert "SUPPORTIVE" not in result

        # No match
        result = softwiki_claim_query(actor="NonExistentActor99999")
        assert "No claims found" in result
    finally:
        _teardown_phase1_workspace(temp_ws)


def test_wiki_read():
    temp_ws = "data/test_phase1_wiki_read_ws"
    try:
        _setup_phase1_workspace(temp_ws)

        # Page not yet generated
        result = softwiki_wiki_read("second-impact")
        assert "not found" in result
        assert "wiki_build" in result

        # Write a fake wiki page and read it back
        from softwiki.config import get_export_dir
        wiki_dir = get_export_dir("wiki/topics")
        wiki_path = os.path.join(wiki_dir, "second-impact.md")
        with open(wiki_path, "w", encoding="utf-8") as f:
            f.write(
                "# The Second Impact\n\n"
                "The Second Impact occurred on September 13, 2000, "
                "when SEELE's contact experiment with Adam triggered a catastrophic explosion in Antarctica."
            )

        result = softwiki_wiki_read("second-impact")
        assert "Second Impact" in result
        assert "Antarctica" in result
        assert "SEELE" in result
    finally:
        _teardown_phase1_workspace(temp_ws)
