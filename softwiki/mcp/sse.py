"""MCP SSE server — exposes SoftWiki tools over HTTP for agent integration (Hermes, etc.)."""

import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from softwiki.config import get_workspace_dir

def create_sse_app():
    """Create a FastMCP SSE app with all SoftWiki tools."""
    from mcp.server.fastmcp import FastMCP
    from starlette.applications import Starlette
    from starlette.routing import Mount

    mcp = FastMCP("SoftWiki", instructions="SoftWiki knowledge base MCP server")

    # ── Register all tools ──
    # We import and replicate the tool registration from server.py
    # without the print redirection side effects

    from softwiki.source_store.db import SessionLocal
    from softwiki.source_store.models import Document, Claim, Chunk, Entity, Relationship, Event
    from softwiki.config import get_config_path, is_module_enabled, get_export_dir, get_enabled_modules, set_enabled_modules, set_workspace_modules

    # ── Ask tool ──
    @mcp.tool()
    def ask(query: str, mode: str = "normal") -> str:
        """Ask a research question against the active workspace.
        Args:
            query: Your research question in natural language.
            mode: Answer style — "normal", "deep", "concise", "creative".
        """
        from softwiki.intelligence.answer_engine import AnswerEngine
        db = SessionLocal()
        try:
            engine = AnswerEngine()
            return engine.ask(db, query, mode=mode)
        except Exception as e:
            return f"Ask failed: {e}"
        finally:
            db.close()

    # ── Ingest URL ──
    @mcp.tool()
    def ingest_url(url: str, source_id: str = "") -> str:
        """Ingest content from a web URL into the knowledge base.
        Args:
            url: The URL to ingest.
            source_id: Optional source identifier.
        """
        db = SessionLocal()
        try:
            from softwiki.ingestion.web_loader import extract_web_content
            from softwiki.ingestion.dedup import calculate_hash, is_duplicate_hash, is_duplicate_url
            from softwiki.source_store.document_repo import DocumentRepository
            from softwiki.intelligence.scope_guard import check_scope
            from softwiki.extraction.processor import run_extraction_pipeline
            from datetime import datetime

            content = extract_web_content(url)
            content["url"] = url
            raw_text = content["raw_text"]
            cleaned_text = content["cleaned_text"]

            text_hash = calculate_hash(cleaned_text)
            if is_duplicate_hash(db, text_hash):
                return "Skipped: duplicate content."
            if is_duplicate_url(db, url):
                return "Skipped: duplicate URL."

            doc = Document(
                title=content.get("title", "Untitled"),
                url=url,
                source_name="MCP Ingest",
                source_type="mcp",
                hash=text_hash,
                raw_text=raw_text,
                cleaned_text=cleaned_text,
                collected_at=datetime.utcnow(),
            )
            doc = DocumentRepository.create_document(db, doc)
            run_extraction_pipeline(db, doc.id, cleaned_text, content.get("published_at"), background=True)
            return f"Ingested: {doc.title} (id={doc.id})"
        except Exception as e:
            return f"Ingest failed: {e}"
        finally:
            db.close()

    @mcp.tool()
    def ingest_file(file_name: str, file_data: str, source_id: str = "") -> str:
        """Ingest a file (base64-encoded) into the knowledge base.
        Args:
            file_name: Original filename (e.g. 'lsl-overview.md').
            file_data: Base64-encoded file content.
            source_id: Optional source identifier.
        """
        import base64, tempfile
        from softwiki.ingestion.dedup import calculate_hash, is_duplicate_hash
        from softwiki.source_store.document_repo import DocumentRepository
        from softwiki.extraction.processor import run_extraction_pipeline
        from datetime import datetime

        try:
            raw = base64.b64decode(file_data)
        except Exception:
            return "Error: invalid base64 data."

        is_md = file_name.lower().endswith(".md")
        title = file_name.replace(".md", "").replace("_", " ").replace("-", " ").title()

        if is_md:
            text = raw.decode("utf-8", errors="replace")
            # Save to raw/md/
            raw_md_dir = os.path.join(get_workspace_dir(), "raw", "md")
            os.makedirs(raw_md_dir, exist_ok=True)
            with open(os.path.join(raw_md_dir, file_name), "w", encoding="utf-8") as f:
                f.write(text)
            from softwiki.source_store.models import Document
            db = SessionLocal()
            try:
                text_hash = calculate_hash(text)
                if is_duplicate_hash(db, text_hash):
                    return f"Skipped: '{file_name}' is a duplicate."
                doc = Document(
                    title=title, url=None,
                    source_name="MCP Ingest", source_type="mcp",
                    hash=text_hash, raw_text=text, cleaned_text=text,
                    collected_at=datetime.utcnow(),
                )
                doc = DocumentRepository.create_document(db, doc)
                run_extraction_pipeline(db, doc.id, text, None, background=True)
                return f"Ingested: {title} (id={doc.id})"
            finally:
                db.close()
        else:
            # Non-md: save to temp file and use the same flow as PDF
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_name)[1]) as tmp:
                tmp.write(raw)
                tmppath = tmp.name
            from softwiki.ingestion.pdf_loader import extract_pdf_content
            from softwiki.source_store.models import Document
            content = extract_pdf_content(tmppath)
            content["url"] = None
            os.unlink(tmppath)
            db = SessionLocal()
            try:
                cleaned = content.get("cleaned_text", "")
                text_hash = calculate_hash(cleaned)
                if is_duplicate_hash(db, text_hash):
                    return f"Skipped: '{file_name}' is a duplicate."
                doc = Document(
                    title=content.get("title") or title, url=None,
                    source_name="MCP Ingest", source_type="mcp",
                    hash=text_hash, raw_text=content.get("raw_text", ""), cleaned_text=cleaned,
                    collected_at=datetime.utcnow(),
                )
                doc = DocumentRepository.create_document(db, doc)
                run_extraction_pipeline(db, doc.id, cleaned, content.get("published_at"), background=True)
                return f"Ingested: {doc.title} (id={doc.id})"
            finally:
                db.close()

    @mcp.tool()
    def rebuild_index() -> str:
        """Rebuild search indexes and auto-generate wiki pages."""
        import subprocess, sys
        from softwiki.source_store.db import SessionLocal, init_tables
        from softwiki.source_store.models import Document, Chunk
        from softwiki.rag.chunker import build_document_chunks
        from softwiki.rag.embedder import WikiEmbedder
        from softwiki.rag.vector_store import LocalVectorStore
        from softwiki.rag.bm25_store import Bm25Store
        from softwiki.source_store.document_repo import DocumentRepository
        from softwiki.wiki.page_generator import WikiPageGenerator
        import yaml

        db = SessionLocal()
        try:
            documents = DocumentRepository.get_all_documents(db)
            if not documents:
                return "No documents to index."
            for doc in documents:
                DocumentRepository.delete_document_chunks(db, doc.id)
                meta = {"title": doc.title, "source_name": doc.source_name, "published_at": doc.published_at}
                chunks_data = build_document_chunks(doc.id, doc.cleaned_text, meta)
                db_chunks = [Chunk(document_id=c["document_id"], chunk_index=c["chunk_index"],
                    text=c["text"], title=c["title"], section=c["section"], published_at=c["published_at"])
                    for c in chunks_data]
                DocumentRepository.create_chunks(db, db_chunks)
            all_chunks = DocumentRepository.get_all_chunks(db)
            embedder = WikiEmbedder()
            vector_store = LocalVectorStore()
            chunk_ids = [c.id for c in all_chunks]
            chunk_texts = [c.text for c in all_chunks]
            embeddings = embedder.embed_texts(chunk_texts)
            if os.path.exists(vector_store.get_current_path()):
                os.remove(vector_store.get_current_path())
                vector_store.load()
            vector_store.add_vectors(chunk_ids, embeddings)
            bm25_store = Bm25Store()
            bm25_store.rebuild_index({c.id: c.text for c in all_chunks})
            # Auto-build wiki
            try:
                wiki_db = SessionLocal()
                gen = WikiPageGenerator()
                topics_path = get_config_path("topics.yaml")
                if os.path.exists(topics_path):
                    with open(topics_path, encoding="utf-8") as f:
                        td = yaml.safe_load(f) or {}
                    for topic in list(td.get("topics", td).keys()):
                        try:
                            gen.generate_topic_page(wiki_db, topic)
                        except Exception:
                            pass
                wiki_db.close()
            except Exception:
                pass
            return f"Indexed {len(all_chunks)} chunks. Wiki pages auto-built."
        finally:
            db.close()

    @mcp.tool()
    def workspace_set(name: str) -> str:
        """Switch to a different workspace.
        Args:
            name: Workspace name (e.g. 'lsl-kb', 'eva-kb').
        """
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ws_path = os.path.join(project_root, "..", "workspace", name)
        ws_path = os.path.abspath(ws_path)
        softwiki_dir = os.path.join(ws_path, ".softwiki")
        if not os.path.isdir(softwiki_dir):
            return f"Workspace '{name}' not found or not initialized."
        os.environ["WORKSPACE_DIR"] = ws_path
        return f"Switched to '{name}'."

    # ── Search / query tools ──
    @mcp.tool()
    def search(query: str, top_k: int = 5) -> str:
        """Search documents in the knowledge base.
        Args:
            query: Search query.
            top_k: Number of results (default 5).
        """
        db = SessionLocal()
        try:
            from softwiki.rag.hybrid_search import HybridSearcher
            searcher = HybridSearcher()
            results = searcher.search(db, query, top_k=top_k)
            if not results:
                return "No results found."
            lines = []
            for r in results:
                chunk = r["chunk"]
                doc = r["document"]
                score = f"{r['score']:.3f}"
                lines.append(f"[{score}] {doc.title}: {chunk.text[:200]}")
            return "\n\n".join(lines)
        finally:
            db.close()

    @mcp.tool()
    def list_documents() -> str:
        """List all documents in the knowledge base."""
        db = SessionLocal()
        try:
            docs = db.query(Document).order_by(Document.id.desc()).all()
            if not docs:
                return "No documents."
            return "\n".join(f"- [{d.id}] {d.title} ({d.source_name})" for d in docs)
        finally:
            db.close()

    @mcp.tool()
    def list_entities() -> str:
        """List all entities in the knowledge graph."""
        db = SessionLocal()
        try:
            entities = db.query(Entity).all()
            if not entities:
                return "No entities."
            return "\n".join(f"- {e.name} [{e.type or '?'}]" for e in entities)
        finally:
            db.close()

    @mcp.tool()
    def list_claims(topic: str = "") -> str:
        """List claims, optionally filtered by topic.
        Args:
            topic: Optional topic filter.
        """
        db = SessionLocal()
        try:
            q = db.query(Claim)
            if topic:
                q = q.filter(Claim.topic == topic)
            claims = q.order_by(Claim.published_at.desc()).limit(20).all()
            if not claims:
                return "No claims."
            return "\n".join(f"- [{c.stance}] {c.actor}: {c.text[:120]}" for c in claims)
        finally:
            db.close()

    @mcp.tool()
    def list_timeline() -> str:
        """List timeline events in chronological order."""
        db = SessionLocal()
        try:
            events = db.query(Event).order_by(Event.event_date.asc()).all()
            if not events:
                return "No events."
            return "\n".join(f"- [{ev.event_date}] {ev.title}" for ev in events)
        finally:
            db.close()

    @mcp.tool()
    def list_workspaces() -> str:
        """List available workspaces and show which is active."""
        from softwiki.config import list_workspaces, get_workspace_dir
        ws_list = list_workspaces()
        active = os.path.basename(get_workspace_dir())
        return f"Active: {active}\nAvailable: {', '.join(ws_list)}"

    @mcp.tool()
    def graph_query(entity_name: str) -> str:
        """Find relationships for a specific entity.
        Args:
            entity_name: Name of the entity to query.
        """
        db = SessionLocal()
        try:
            rels = db.query(Relationship).filter(
                (Relationship.source_name == entity_name) | (Relationship.target_name == entity_name)
            ).all()
            if not rels:
                return f"No relationships found for '{entity_name}'."
            return "\n".join(f"- {r.source_name} --({r.relation_type})--> {r.target_name}" for r in rels)
        finally:
            db.close()

    @mcp.tool()
    def wiki_list() -> str:
        """List available wiki topics."""
        import yaml
        topics_path = get_config_path("topics.yaml")
        if not os.path.exists(topics_path):
            return "No topics configured."
        with open(topics_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        topics = data.get("topics", data)
        lines = []
        for key, info in topics.items():
            group = info.get("group", "")
            name = info.get("name", key)
            lines.append(f"  [{group}] {name} ({key})")
        return "\n".join(lines) if lines else "No topics."

    @mcp.tool()
    def wiki_read(topic: str) -> str:
        """Read a compiled wiki page.
        Args:
            topic: Topic key (e.g. 'shinji-ikari').
        """
        export_dir = get_export_dir("wiki/topics")
        filepath = os.path.join(export_dir, f"{topic}.md")
        if not os.path.exists(filepath):
            return f"Wiki page '{topic}' not found. Build it first."
        with open(filepath, encoding="utf-8") as f:
            return f.read()

    # ── Module management ──
    @mcp.tool()
    def modules_list() -> str:
        """List all knowledge modules and their enabled/disabled status."""
        ws_path = get_workspace_dir()
        ws_config = os.path.join(ws_path, ".softwiki", "modules.json")
        has_override = os.path.exists(ws_config)
        lines = ["## Knowledge Modules", ""]
        for name in ["rag", "graph", "claimdb", "timeline", "llmwiki"]:
            status = "✅ enabled" if is_module_enabled(name) else "❌ disabled"
            lines.append(f"- **{name}**: {status}")
        lines.append("")
        lines.append(f"Source: {'workspace config' if has_override else 'global default'}")
        return "\n".join(lines)

    @mcp.tool()
    def modules_set(enabled: str, scope: str = "global") -> str:
        """Enable or disable knowledge modules.
        Args:
            enabled: Comma-separated list (e.g. "rag,graph,claimdb")
            scope: "global" or "workspace"
        """
        valid = {"rag", "graph", "claimdb", "timeline", "llmwiki"}
        modules = [m.strip().lower() for m in enabled.split(",") if m.strip().lower() in valid]
        if scope == "workspace":
            set_workspace_modules(modules)
        else:
            set_enabled_modules(modules)
        return modules_list()

    # ── Get the SSE app ──
    sse = mcp.sse_app()
    return sse
