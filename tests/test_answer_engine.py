import os
from datetime import datetime
from softwiki.source_store.db import Base, get_engine, SessionLocal
from softwiki.source_store.models import Document, Chunk
from softwiki.source_store.document_repo import DocumentRepository
from softwiki.intelligence.answer_engine import AnswerEngine
from softwiki.rag.vector_store import LocalVectorStore
from softwiki.rag.bm25_store import Bm25Store
from softwiki.rag.embedder import WikiEmbedder

def test_answer_engine_integration():
    db_dir = "data/test_workspace_ae"
    os.makedirs(db_dir, exist_ok=True)
    os.environ["WORKSPACE_DIR"] = db_dir
    
    # Initialize engine & tables dynamically
    engine = get_engine()
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # Clean up in case of leftovers
        db.query(Chunk).delete()
        db.query(Document).delete()
        db.commit()

        doc = Document(
            title="Participant A's Stance on Project Alpha Protocol",
            url="https://reuters.com/participant-a-protocol",
            source_name="Reuters",
            source_type="news",
            source_country="uk",
            trust_level="high",
            language="en",
            author="John Doe",
            raw_text="Participant A is cautious about a common Project Alpha protocol. Core developer Jaishankar said New Delhi prefers focusing on local interface adaptation to boost compatibility instead of establishing a new shared protocol.",
            cleaned_text="Participant A is cautious about a common Project Alpha protocol. Core developer Jaishankar said New Delhi prefers focusing on local interface adaptation to boost compatibility instead of establishing a new shared protocol.",
            hash="test_hash_value_123",
            published_at=datetime(2024, 10, 23),
            collected_at=datetime.utcnow()
        )
        doc = DocumentRepository.create_document(db, doc)
        
        c1 = Chunk(
            document_id=doc.id,
            chunk_index=0,
            text="[Document: Participant A's Stance on Project Alpha Protocol | Source: Reuters]\nParticipant A is cautious about a common Project Alpha protocol. Core developer Jaishankar said New Delhi prefers focusing on local interface adaptation to boost compatibility instead of establishing a new shared protocol.",
            title=doc.title,
            section="General",
            published_at=doc.published_at
        )
        DocumentRepository.create_chunks(db, [c1])

        # Build indices
        v_store = LocalVectorStore()
        b_store = Bm25Store()
        
        embedder = WikiEmbedder()
        emb = embedder.embed_query(c1.text)
        
        v_store.add_vectors([c1.id], [emb])
        b_store.rebuild_index({c1.id: c1.text})

        # Run Q&A
        engine_obj = AnswerEngine()
        # Mock load configs to bypass config file reads
        engine_obj.model_name = "gpt-4o"
        engine_obj.temperature = 0.2
        
        answer = engine_obj.ask(db, "Is Participant A supportive of a common protocol?")
        
        assert "Direct Answer" in answer
        assert "Evidence Summary" in answer
        assert "Reuters" in answer

    finally:
        db.close()
        # Clean up database file and workspace dir
        import shutil
        if os.path.exists(db_dir):
            shutil.rmtree(db_dir)
        # Reset environment variable
        del os.environ["WORKSPACE_DIR"]
