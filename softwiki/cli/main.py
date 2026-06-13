import os
import sys
import click
import shutil
import yaml
from datetime import datetime
from softwiki.source_store.db import SessionLocal, init_tables
from softwiki.source_store.models import Document, Chunk, SourceConfig
from softwiki.source_store.document_repo import DocumentRepository
from softwiki.ingestion.web_loader import extract_web_content
from softwiki.ingestion.pdf_loader import extract_pdf_content
from softwiki.ingestion.dedup import calculate_hash, is_duplicate_hash, is_duplicate_url
from softwiki.rag.chunker import build_document_chunks
from softwiki.rag.embedder import WikiEmbedder
from softwiki.rag.vector_store import LocalVectorStore
from softwiki.rag.bm25_store import Bm25Store
from softwiki.extraction.claim_extractor import ClaimExtractor
from softwiki.extraction.processor import run_extraction_pipeline
from softwiki.intelligence.answer_engine import AnswerEngine
from softwiki.wiki.page_generator import WikiPageGenerator
from softwiki.config import get_workspace_dir, get_config_path, get_raw_dir, get_processed_dir, get_export_dir, is_module_enabled, get_session_id

@click.group()
@click.option('--workspace', '-w', type=str, default=None, help='Path to the workspace directory.')
@click.option('--mode', type=click.Choice(['wiki-admin', 'wiki-manage', 'wiki-study', 'wiki-work']), default='wiki-admin', help='Execution mode (wiki-admin, wiki-manage, wiki-study, wiki-work).')
@click.option('--session-id', type=str, default=None, help='Session ID for output routing (only used in user modes).')
def cli(workspace, mode, session_id):
    """Universal Domain-Independent Research Wiki and RAG Engine"""
    if workspace:
        os.environ["WORKSPACE_DIR"] = os.path.abspath(workspace)
    
    os.environ["SOFTWIKI_MODE"] = mode
    if session_id:
        os.environ["SOFTWIKI_SESSION_ID"] = session_id
        
    # Ensure active workspace directories are printed
    click.echo(f"[*] Active Workspace: {get_workspace_dir()}")
    if mode in ["wiki-study", "wiki-work", "study", "work"]:
        active_sess = get_session_id()
        click.echo(f"[*] User Mode Active ({mode.upper()}). Session Output: output/{active_sess}/")

@cli.command()
def init():
    """Initialize folders, configs, and database for the active workspace."""
    if os.getenv("SOFTWIKI_MODE") in ["wiki-study", "wiki-work", "study", "work"]:
        click.echo("Error: Write operations (init) are disabled in wiki-study/wiki-work modes.", err=True)
        sys.exit(1)
    ws = get_workspace_dir()
    click.echo(f"Initializing workspace at: {ws}...")
    
    # 1. Create subfolders
    get_raw_dir("html")
    get_raw_dir("pdf")
    get_raw_dir("markdown")
    get_raw_dir("api")
    get_processed_dir("documents")
    get_processed_dir("chunks")
    get_processed_dir("embeddings")
    get_processed_dir("extracted")
    get_export_dir("wiki/countries")
    get_export_dir("wiki/organizations")
    get_export_dir("wiki/topics")
    get_export_dir("wiki/events")
    get_export_dir("wiki/claims")
    get_export_dir("wiki/reports")
    
    # 2. Copy default configs from root configs/ folder if workspace config is empty and root configs exists
    config_names = ["sources.yaml", "model_profiles.yaml"]
    os.makedirs(os.path.join(ws, "configs"), exist_ok=True)
    
    templates_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "templates"))
    for cfg in config_names:
        dest_cfg_path = get_config_path(cfg)
        if not os.path.exists(dest_cfg_path):
            src_cfg_path = os.path.join(templates_dir, cfg)
            if os.path.exists(src_cfg_path):
                shutil.copy(src_cfg_path, dest_cfg_path)
                click.echo(f"Copied default config: {cfg}")
            else:
                # Write minimal placeholders if root configs are absent
                with open(dest_cfg_path, "w", encoding="utf-8") as f:
                    if cfg == "sources.yaml":
                        yaml.safe_dump({"sources": []}, f)
                    elif cfg == "topics.yaml":
                        yaml.safe_dump({"topics": {}}, f)
                    elif cfg == "model_profiles.yaml":
                        yaml.safe_dump({"profiles": {}}, f)
                click.echo(f"Created placeholder config: {cfg}")

    # 2b. Copy default scope.md template
    dest_scope_path = os.path.join(ws, "scope.md")
    if not os.path.exists(dest_scope_path):
        src_scope_path = os.path.join(templates_dir, "scope.md")
        if os.path.exists(src_scope_path):
            shutil.copy(src_scope_path, dest_scope_path)
            click.echo("Copied default scope: scope.md")
        else:
            with open(dest_scope_path, "w", encoding="utf-8") as f:
                f.write(
                    "# Knowledge Base Scope\n\n"
                    "Define the topics, domains, and themes that are within the scope of this knowledge base.\n\n"
                    "## In Scope\n"
                    "- Example topic: De-dollarization, central bank reserves, gold, and international trade currencies.\n\n"
                    "## Out of Scope\n"
                    "- Unrelated financial news, stock market updates, recipes, entertainment, sports, and general chat.\n"
                )
            click.echo("Created placeholder scope: scope.md")

    # 3. Create database tables
    init_tables()
    click.echo("Database initialized successfully.")

    # 4. Seed predefined sources from workspace sources.yaml
    sources_yaml_path = get_config_path("sources.yaml")
    if os.path.exists(sources_yaml_path):
        click.echo("Seeding sources in workspace...")
        with open(sources_yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            sources = data.get("sources", [])
        
        db = SessionLocal()
        try:
            for s in sources:
                source_obj = SourceConfig(
                    id=s.get("id"),
                    name=s.get("name"),
                    type=s.get("type"),
                    url=s.get("url"),
                    trust_level=s.get("trust_level"),
                    source_country=s.get("source_country"),
                    language=s.get("language")
                )
                DocumentRepository.save_source_config(db, source_obj)
                click.echo(f"Seeded source: {s.get('id')} ({s.get('name')})")
            db.commit()
        finally:
            db.close()
            
    click.echo("Workspace initialization completed.")

@cli.command()
@click.option('--url', type=str, help='Ingest content from a web URL')
@click.option('--file', type=str, help='Ingest content from a local PDF file')
@click.option('--source-id', type=str, help='Associate with a predefined source ID in workspace configs/sources.yaml')
def ingest(url, file, source_id):
    """Ingest a document, clean it, and save to workspace database."""
    if os.getenv("SOFTWIKI_MODE") in ["wiki-study", "wiki-work", "study", "work"]:
        click.echo("Error: Write operations (ingest) are disabled in wiki-study/wiki-work modes.", err=True)
        sys.exit(1)
    if not url and not file:
        click.echo("Error: Please provide either --url or --file", err=True)
        sys.exit(1)

    db = SessionLocal()
    try:
        source_meta = {}
        if source_id:
            src_config = DocumentRepository.get_source_config(db, source_id)
            if src_config:
                source_meta = {
                    "source_name": src_config.name,
                    "source_type": src_config.type,
                    "source_country": src_config.source_country,
                    "trust_level": src_config.trust_level,
                    "language": src_config.language
                }
            else:
                click.echo(f"Warning: Predefined source '{source_id}' not found in database. Using defaults.")

        if url:
            click.echo(f"Ingesting URL: {url}...")
            content = extract_web_content(url)
            content["url"] = url
        else:
            click.echo(f"Ingesting PDF: {file}...")
            content = extract_pdf_content(file)
            content["url"] = None

        title = content["title"]
        author = content["author"]
        raw_text = content["raw_text"]
        cleaned_text = content["cleaned_text"]
        published_at = content["published_at"]

        # Check scope
        from softwiki.intelligence.scope_guard import check_scope
        is_in_scope, reason = check_scope(f"Title: {title}\nContent:\n{cleaned_text[:2000]}", item_type="document")
        if not is_in_scope:
            click.echo(f"Skip: Document content is out of scope. Reason: {reason}")
            sys.exit(0)

        text_hash = calculate_hash(cleaned_text)
        if is_duplicate_hash(db, text_hash):
            click.echo("Skip: Document with identical content hash already exists.")
            sys.exit(0)
        if url and is_duplicate_url(db, url):
            click.echo("Skip: Document with identical URL already exists.")
            sys.exit(0)

        doc = Document(
            title=title,
            url=url,
            source_name=source_meta.get("source_name", "Manual Import"),
            source_type=source_meta.get("source_type", "manual_import"),
            source_country=source_meta.get("source_country", "unknown"),
            trust_level=source_meta.get("trust_level", "medium"),
            language=source_meta.get("language", "en"),
            author=author,
            raw_text=raw_text,
            cleaned_text=cleaned_text,
            hash=text_hash,
            published_at=published_at,
            collected_at=datetime.utcnow()
        )
        
        doc = DocumentRepository.create_document(db, doc)
        click.echo(f"Created Document ID {doc.id}: '{doc.title}'")

        click.echo("Running extraction pipeline...")
        ext_results = run_extraction_pipeline(db, doc.id, cleaned_text, published_at)
        click.echo(f"Extraction complete: {ext_results.get('claims', 0)} claims, "
                   f"{ext_results.get('entities', 0)} entities, "
                   f"{ext_results.get('relationships', 0)} relationships, "
                   f"{ext_results.get('events', 0)} events extracted.")

    except Exception as e:
        click.echo(f"Ingestion failed: {e}", err=True)
        sys.exit(1)
    finally:
        db.close()

@cli.command()
def index():
    """Build and update search indexes for the workspace."""
    if os.getenv("SOFTWIKI_MODE") in ["wiki-study", "wiki-work", "study", "work"]:
        click.echo("Error: Write operations (index) are disabled in wiki-study/wiki-work modes.", err=True)
        sys.exit(1)
    db = SessionLocal()
    try:
        click.echo("Building search indexes...")
        
        documents = DocumentRepository.get_all_documents(db)
        if not documents:
            click.echo("No documents found in database. Ingest some documents first.")
            sys.exit(0)

        for doc in documents:
            DocumentRepository.delete_document_chunks(db, doc.id)
            
            meta = {
                "title": doc.title,
                "source_name": doc.source_name,
                "published_at": doc.published_at
            }
            chunks_data = build_document_chunks(doc.id, doc.cleaned_text, meta)
            
            db_chunks = []
            for cd in chunks_data:
                db_chunks.append(Chunk(
                    document_id=cd["document_id"],
                    chunk_index=cd["chunk_index"],
                    text=cd["text"],
                    title=cd["title"],
                    section=cd["section"],
                    published_at=cd["published_at"]
                ))
            DocumentRepository.create_chunks(db, db_chunks)

        all_chunks = DocumentRepository.get_all_chunks(db)
        click.echo(f"Indexing {len(all_chunks)} chunks...")

        embedder = WikiEmbedder()
        vector_store = LocalVectorStore()
        
        chunk_ids = [c.id for c in all_chunks]
        chunk_texts = [c.text for c in all_chunks]
        
        click.echo("Generating embeddings...")
        embeddings = embedder.embed_texts(chunk_texts)
        
        if os.path.exists(vector_store.get_current_path()):
            os.remove(vector_store.get_current_path())
            vector_store.load()
            
        vector_store.add_vectors(chunk_ids, embeddings)
        click.echo("Vector index successfully updated.")

        bm25_store = Bm25Store()
        chunk_id_to_text = {c.id: c.text for c in all_chunks}
        bm25_store.rebuild_index(chunk_id_to_text)
        click.echo("BM25 keyword index successfully updated.")
        
        click.echo("Indexing complete!")

    except Exception as e:
        click.echo(f"Indexing failed: {e}", err=True)
        sys.exit(1)
    finally:
        db.close()

@cli.command()
@click.argument('question', type=str)
def ask(question):
    """Query the intelligence system with a research question."""
    db = SessionLocal()
    try:
        engine = AnswerEngine()
        click.echo(f"Researching: \"{question}\"...\n")
        answer = engine.ask(db, question)
        click.echo(answer)
    except Exception as e:
        click.echo(f"Failed to retrieve answer: {e}", err=True)
        sys.exit(1)
    finally:
        db.close()

@cli.group()
def wiki():
    """Wiki page generation management."""
    pass

@wiki.command(name="build")
@click.option('--topic', type=str, required=True, help='Topic ID to build page for')
def wiki_build(topic):
    """Build a markdown wiki page for a given topic."""
    if os.getenv("SOFTWIKI_MODE") in ["wiki-study", "study"]:
        click.echo("Error: Wiki compilation is disabled in wiki-study mode.", err=True)
        sys.exit(1)
    db = SessionLocal()
    try:
        generator = WikiPageGenerator()
        click.echo(f"Generating wiki page for topic: '{topic}'...")
        filepath = generator.generate_topic_page(db, topic)
        click.echo(f"Wiki page successfully written to: {filepath}")
    except Exception as e:
        click.echo(f"Failed to build wiki page: {e}", err=True)
        sys.exit(1)
    finally:
        db.close()

@cli.command()
@click.option('--workspace', '-w', type=str, default=None,
              help='Workspace to open (name under workspace/ or absolute path). '
                   'Defaults to WORKSPACE_DIR env var, or workspace/default.')
@click.option('--model', '-m', type=str, default=None,
              help='Model to use for analysis (e.g. gemini-2.5-flash). '
                   'Defaults to ANALYSIS_MODEL env var or gemini-2.5-flash.')
@click.option('--session', '-s', type=str, default=None,
              help='Custom session name suffix. Final session ID = {workspace}-{mode}-{session}. '
                   'Useful to keep separate conversation threads within the same workspace+mode.')
def shell(workspace, model, session):
    """Launch the interactive research and management shell (TUI)."""
    # Resolve workspace: flag > env var > default
    if workspace:
        if not os.path.isabs(workspace) and not workspace.startswith('workspace/'):
            candidate = os.path.join('workspace', workspace)
            if os.path.isdir(candidate):
                workspace = candidate
        os.environ['WORKSPACE_DIR'] = os.path.abspath(workspace)
    elif not os.environ.get('WORKSPACE_DIR'):
        os.environ['WORKSPACE_DIR'] = os.path.abspath('workspace/default')

    from softwiki.config import get_workspace_dir
    click.echo(f"[*] Workspace: {get_workspace_dir()}")

    from softwiki.cli.shell import start_shell
    start_shell(model_override=model, session_suffix=session)

@cli.command()
@click.option('--port', type=int, default=None, help='Port to run the API server on.')
@click.option('--host', type=str, default=None, help='Host to bind the API server to.')
def api(port, host):
    """Start the REST API server."""
    from softwiki.config import get_api_port, get_host
    port = port or get_api_port()
    host = host or get_host()
    import uvicorn
    click.echo(f"Starting API server on http://{host}:{port}...")
    uvicorn.run("softwiki.api.server:app", host=host, port=port, reload=False)

@cli.command()
@click.option('--port', type=int, default=None, help='Port to run the MCP SSE server on.')
@click.option('--host', type=str, default=None, help='Host to bind the MCP server to.')
def mcp(port, host):
    """Start the MCP server in SSE mode (for agent integration)."""
    from softwiki.config import get_mcp_port, get_host
    port = port or get_mcp_port()
    host = host or get_host()
    import uvicorn
    from softwiki.mcp.sse import create_sse_app
    app = create_sse_app()
    click.echo(f"Starting MCP SSE server on http://{host}:{port}...")
    uvicorn.run(app, host=host, port=port, reload=False)

@cli.group()
def graph():
    """Graph database management."""
    pass

@graph.command(name="list")
def graph_list():
    """List all extracted entities and relationships in the workspace."""
    db = SessionLocal()
    try:
        entities = DocumentRepository.get_all_entities(db)
        relationships = DocumentRepository.get_all_relationships(db)
        
        click.echo(f"=== Entities ({len(entities)}) ===")
        for ent in entities:
            click.echo(f"- {ent.name} [{ent.type or 'unknown'}]: {ent.description or 'No description'}")
            
        click.echo(f"\n=== Relationships ({len(relationships)}) ===")
        for rel in relationships:
            click.echo(f"- {rel.source_name} --({rel.relation_type})--> {rel.target_name} (Conf: {rel.confidence:.2f})")
            if rel.description:
                click.echo(f"  Note: {rel.description}")
    except Exception as e:
        click.echo(f"Failed to query graph: {e}", err=True)
    finally:
        db.close()

@cli.group()
def timeline():
    """Timeline events management."""
    pass

@timeline.command(name="list")
def timeline_list():
    """List all chronological events in the workspace."""
    db = SessionLocal()
    try:
        events = DocumentRepository.get_all_events(db)
        # sort chronologically
        events = sorted(events, key=lambda x: x.event_date)
        
        click.echo(f"=== Chronological Events ({len(events)}) ===")
        for ev in events:
            date_str = ev.event_date.strftime("%Y-%m-%d")
            click.echo(f"- [{date_str}] {ev.title} (Topic: {ev.topic})")
            if ev.description:
                click.echo(f"  Description: {ev.description}")
    except Exception as e:
        click.echo(f"Failed to query timeline: {e}", err=True)
    finally:
        db.close()

if __name__ == '__main__':
    cli()


