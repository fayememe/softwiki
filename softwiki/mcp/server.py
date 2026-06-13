import os
import sys
import builtins

# Save the original print function
_original_print = builtins.print

# Define wrapper to redirect standard prints to sys.stderr to avoid corrupting JSON-RPC stdout
def _stderr_print(*args, **kwargs):
    if kwargs.get("file") is None or kwargs.get("file") == sys.stdout:
        kwargs["file"] = sys.stderr
    _original_print(*args, **kwargs)

builtins.print = _stderr_print

from datetime import datetime
from mcp.server.fastmcp import FastMCP

# Ensure parent directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from softwiki.config import get_workspace_dir, get_db_url, get_export_dir
from softwiki.source_store.db import SessionLocal, init_tables
from softwiki.source_store.models import Document, Claim, Chunk
from softwiki.source_store.document_repo import DocumentRepository
from softwiki.ingestion.web_loader import extract_web_content
from softwiki.ingestion.pdf_loader import extract_pdf_content
from softwiki.ingestion.dedup import calculate_hash, is_duplicate_hash, is_duplicate_url
from softwiki.extraction.processor import run_extraction_pipeline
from softwiki.rag.chunker import build_document_chunks
from softwiki.rag.embedder import WikiEmbedder
from softwiki.rag.vector_store import LocalVectorStore
from softwiki.rag.bm25_store import Bm25Store
from softwiki.rag.hybrid_search import HybridSearcher
from softwiki.wiki.page_generator import WikiPageGenerator

mcp = FastMCP("softwiki")

@mcp.tool()
def status() -> str:
    """Get the status of the active Softwiki workspace, including database stats."""
    ws = get_workspace_dir()
    db = SessionLocal()
    try:
        doc_count = db.query(Document).count()
        claim_count = db.query(Claim).count()
        chunk_count = db.query(Chunk).count()
        db_url = get_db_url()
        return (
            f"Active Workspace: {ws}\n"
            f"Database URL: {db_url}\n"
            f"Documents Count: {doc_count}\n"
            f"Chunks Count: {chunk_count}\n"
            f"Claims Count: {claim_count}"
        )
    except Exception as e:
        return f"Error getting status: {e}"
    finally:
        db.close()

@mcp.tool()
def ingest(url: str = None, file: str = None, source_id: str = None) -> str:
    """Ingest a new document from a URL or a local PDF file into the active workspace.

    Args:
        url: The web URL to crawl and ingest.
        file: The absolute path to a local PDF file to ingest.
        source_id: Optional source ID from workspace config/sources.yaml to associate metadata.
    """
    if os.getenv("SOFTWIKI_MODE") in ["study", "work", "user", "wiki-study", "wiki-work", "wiki-user"]:
        return f"Error: Write operations (ingest) are disabled in {os.getenv('SOFTWIKI_MODE')} mode."
    if not url and not file:
        return "Error: You must provide either 'url' or 'file'."
        
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
                
        from softwiki.ingestion.file_store import (
            save_raw_html, save_raw_pdf, save_processed_document
        )

        if url:
            content = extract_web_content(url)
            content["url"] = url
        else:
            if not os.path.isabs(file):
                file = os.path.abspath(file)
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
            return f"Skip: Document content is out of scope. Reason: {reason}"

        text_hash = calculate_hash(cleaned_text)
        if is_duplicate_hash(db, text_hash):
            return "Skip: Document with identical content hash already exists."
        if url and is_duplicate_url(db, url):
            return "Skip: Document with identical URL already exists."

        doc = Document(
            title=title,
            url=url,
            source_name=source_meta.get("source_name", "Manual Import"),
            source_type=source_meta.get("source_type", "manual_import"),
            source_country=source_meta.get("source_country", "unknown"),
            trust_level=source_meta.get("trust_level", "medium"),
            language=source_meta.get("language") or content.get("language", "unknown"),
            author=author,
            raw_text=raw_text,
            cleaned_text=cleaned_text,
            hash=text_hash,
            published_at=published_at,
            collected_at=datetime.utcnow()
        )

        doc = DocumentRepository.create_document(db, doc)
        doc_id = doc.id

        # Stage 1: save raw source file
        try:
            if url and content.get("raw_html"):
                save_raw_html(text_hash, content["raw_html"])
            elif file:
                save_raw_pdf(doc_id, file)
        except Exception as e:
            print(f"[file_store] raw save failed: {e}", file=sys.stderr)

        # Stage 2: save processed (cleaned) document text
        try:
            save_processed_document(
                doc_id, title, cleaned_text,
                language=source_meta.get("language") or content.get("language", "unknown"),
                published_at=published_at,
                source_name=source_meta.get("source_name", "Manual Import"),
                url=url or "",
            )
        except Exception as e:
            print(f"[file_store] processed save failed: {e}", file=sys.stderr)

        # Stage 3: chunk + incremental index update
        try:
            from softwiki.ingestion.file_store import save_chunks
            meta = {"title": title, "source_name": source_meta.get("source_name", "Manual Import"), "published_at": published_at}
            chunks_data = build_document_chunks(doc_id, cleaned_text, meta)
            db_chunks = [Chunk(
                document_id=cd["document_id"], chunk_index=cd["chunk_index"],
                text=cd["text"], title=cd["title"], section=cd["section"],
                published_at=cd["published_at"]
            ) for cd in chunks_data]
            DocumentRepository.create_chunks(db, db_chunks)
            save_chunks(doc_id, chunks_data)

            embedder = WikiEmbedder()
            chunk_texts = [cd["text"] for cd in chunks_data]
            db_chunk_ids = [c.id for c in db.query(Chunk).filter(Chunk.document_id == doc_id).all()]
            embeddings = embedder.embed_texts(chunk_texts)
            LocalVectorStore().add_vectors(db_chunk_ids, embeddings)

            bm25_store = Bm25Store()
            bm25_store.add_documents({cid: text for cid, text in zip(db_chunk_ids, chunk_texts)})
        except Exception as e:
            print(f"[ingest] incremental index failed: {e}", file=sys.stderr)

        # Stage 4: run extraction pipeline in background
        run_extraction_pipeline(db, doc_id, cleaned_text, published_at, background=True)

        return (f"Ingested Document ID {doc_id}: '{doc.title}'. "
                f"{len(chunks_data)} chunks indexed. Claim/Graph/Timeline extraction running in background.")
    except Exception as e:
        return f"Ingestion failed: {e}"
    finally:
        db.close()

@mcp.tool()
def index() -> str:
    """Rebuild vector and keyword search indexes for all documents in the active workspace."""
    if os.getenv("SOFTWIKI_MODE") in ["study", "work", "user", "wiki-study", "wiki-work", "wiki-user"]:
        return f"Error: Write operations (index) are disabled in {os.getenv('SOFTWIKI_MODE')} mode."
    db = SessionLocal()
    try:
        documents = DocumentRepository.get_all_documents(db)
        if not documents:
            return "No documents found in database. Ingest some documents first."
            
        from softwiki.ingestion.file_store import save_chunks

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

            # Stage 3: save chunks JSON to disk
            try:
                save_chunks(doc.id, chunks_data)
            except Exception as e:
                print(f"[file_store] chunks save failed doc={doc.id}: {e}", file=sys.stderr)
            
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
        chunk_id_to_text = {c.id: c.text for c in all_chunks}
        bm25_store.rebuild_index(chunk_id_to_text)
        
        return f"Successfully rebuilt index for {len(all_chunks)} chunks."
    except Exception as e:
        return f"Indexing failed: {e}"
    finally:
        db.close()

@mcp.tool()
def search(query: str, top_k: int = 5) -> str:
    """Perform CJK-aware hybrid search on the active workspace.
    
    Args:
        query: The search keywords or natural language query.
        top_k: Number of search results to return (default: 5).
    """
    db = SessionLocal()
    try:
        searcher = HybridSearcher()
        results = searcher.search(db, query, top_k=top_k)
        if not results:
            return "No matching search results found."
            
        formatted = []
        for i, res in enumerate(results, 1):
            chunk = res["chunk"]
            doc = res["document"]
            formatted.append(
                f"[{i}] Title: {doc.title}\n"
                f"Source: {doc.source_name} ({doc.source_type or 'unknown'})\n"
                f"Date: {doc.published_at.strftime('%Y-%m-%d') if doc.published_at else 'unknown'}\n"
                f"Text:\n{chunk.text}\n"
                f"Score: {res['score']:.4f}\n"
                "----------------------------------------"
            )
        return "\n\n".join(formatted)
    except Exception as e:
        return f"Search failed: {e}"
    finally:
        db.close()

@mcp.tool()
def wiki_build(topic: str) -> str:
    """Compile and generate a markdown wiki page for a specific topic ID.
    
    Args:
        topic: The topic ID (e.g. 'de-dollarization') to compile.
    """
    if os.getenv("SOFTWIKI_MODE") in ["study", "wiki-study"]:
        return "Error: Wiki compilation is disabled in study mode."
    db = SessionLocal()
    try:
        generator = WikiPageGenerator()
        filepath = generator.generate_topic_page(db, topic)
        return f"Wiki page successfully compiled and written to: {filepath}"
    except Exception as e:
        return f"Failed to build wiki page: {e}"
    finally:
        db.close()

@mcp.tool()
def ask(query: str, mode: str = "normal") -> str:
    """Ask a research question against the active workspace knowledge base.

    Uses hybrid RAG retrieval, graph context, claims, timeline, and LLM synthesis
    to produce an answer with citations.

    Args:
        query: Your research question in natural language.
        mode: Answer style — "normal" (balanced), "deep" (thorough), "concise" (short), "creative" (exploratory).
    """
    db = SessionLocal()
    try:
        from softwiki.intelligence.answer_engine import AnswerEngine
        engine = AnswerEngine()
        return engine.ask(db, query, mode=mode)
    except Exception as e:
        return f"Ask failed: {e}"
    finally:
        db.close()


def _web_search_tavily(query: str, top_k: int, api_key: str) -> list:
    """Search via Tavily API (https://tavily.com). Recommended for AI/RAG use cases."""
    import requests
    resp = requests.post(
        "https://api.tavily.com/search",
        json={"query": query, "max_results": top_k, "include_answer": False},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=15
    )
    resp.raise_for_status()
    data = resp.json()
    return [
        {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
        for r in data.get("results", [])
    ]


def _web_search_serpapi(query: str, top_k: int, api_key: str) -> list:
    """Search via SerpAPI (https://serpapi.com). Supports Google, Bing, Baidu, etc."""
    import requests
    resp = requests.get(
        "https://serpapi.com/search",
        params={"q": query, "num": top_k, "api_key": api_key, "engine": "google"},
        timeout=15
    )
    resp.raise_for_status()
    data = resp.json()
    return [
        {"title": r.get("title", ""), "url": r.get("link", ""), "snippet": r.get("snippet", "")}
        for r in data.get("organic_results", [])[:top_k]
    ]


def _web_search_bing(query: str, top_k: int, api_key: str) -> list:
    """Search via Bing Web Search API (Azure Cognitive Services)."""
    import requests
    resp = requests.get(
        "https://api.bing.microsoft.com/v7.0/search",
        params={"q": query, "count": top_k, "mkt": "zh-CN"},
        headers={"Ocp-Apim-Subscription-Key": api_key},
        timeout=15
    )
    resp.raise_for_status()
    data = resp.json()
    return [
        {"title": r.get("name", ""), "url": r.get("url", ""), "snippet": r.get("snippet", "")}
        for r in data.get("webPages", {}).get("value", [])[:top_k]
    ]


def _web_search_disabled_check() -> str | None:
    """Returns an error string if web_search is not enabled, else None."""
    if os.getenv("SOFTWIKI_ENABLE_WEB_SEARCH", "").lower() not in ("1", "true", "yes"):
        return (
            "softwiki web_search is disabled on this server. "
            "Set SOFTWIKI_ENABLE_WEB_SEARCH=true to enable it for thin-client use. "
            "Shell users should configure their own client-side search (e.g. Brave Search MCP)."
        )
    return None


@mcp.tool()
def web_search(query: str, top_k: int = 5) -> str:
    """Perform a web search via the server-side search proxy (BYOK, thin-client use only).

    Disabled by default. Set SOFTWIKI_ENABLE_WEB_SEARCH=true on the server to enable.
    Shell users should use their own client-side search MCP instead.

    Supported providers (checked in order):
      - Tavily:  set TAVILY_API_KEY   (recommended, AI-native)
      - SerpAPI: set SERPAPI_KEY      (Google/Bing/Baidu, broad coverage)
      - Bing:    set BING_SEARCH_API_KEY (Azure Cognitive Services)

    If no key is configured, this tool returns a setup instruction.
    External agents (opencode, Claude, Cursor, etc.) may have their own
    web search tools and do not need to use this one.

    Args:
        query: The search keywords or natural language query.
        top_k: Number of results to return (default: 5).
    """
    err = _web_search_disabled_check()
    if err:
        return err

    # Check scope
    from softwiki.intelligence.scope_guard import check_scope
    is_in_scope, reason = check_scope(query, item_type="search_query")
    if not is_in_scope:
        return f"Reject: The search query is out of scope. Reason: {reason}"

    # Try shared web search (DuckDuckGo free + any configured API keys)
    from softwiki.search.web import search_web
    web_results = search_web(query, top_k)
    if web_results:
        return "\n\n".join(web_results)

    tavily_key = os.getenv("TAVILY_API_KEY", "").strip()
    serpapi_key = os.getenv("SERPAPI_KEY", "").strip()
    bing_key = os.getenv("BING_SEARCH_API_KEY", "").strip()

    if not any([tavily_key, serpapi_key, bing_key]):
        return (
            "Web search is not configured. To enable it, add one of the following "
            "to your .env file:\n"
            "  TAVILY_API_KEY=...       (recommended, https://tavily.com)\n"
            "  SERPAPI_KEY=...          (https://serpapi.com)\n"
            "  BING_SEARCH_API_KEY=...  (Azure Cognitive Services)\n\n"
            "Note: DuckDuckGo is also available without any API key."
        )

    results = []
    provider_used = None
    error_log = []

    if tavily_key and not results:
        try:
            results = _web_search_tavily(query, top_k, tavily_key)
            provider_used = "Tavily"
        except Exception as e:
            error_log.append(f"Tavily failed: {e}")
            print(f"[web_search] Tavily error: {e}", file=sys.stderr)

    if serpapi_key and not results:
        try:
            results = _web_search_serpapi(query, top_k, serpapi_key)
            provider_used = "SerpAPI"
        except Exception as e:
            error_log.append(f"SerpAPI failed: {e}")
            print(f"[web_search] SerpAPI error: {e}", file=sys.stderr)

    if bing_key and not results:
        try:
            results = _web_search_bing(query, top_k, bing_key)
            provider_used = "Bing"
        except Exception as e:
            error_log.append(f"Bing failed: {e}")
            print(f"[web_search] Bing error: {e}", file=sys.stderr)

    if not results:
        detail = "; ".join(error_log) if error_log else "No results returned."
        return f"Web search returned no results. Details: {detail}"

    formatted = [f"[Web Search via {provider_used}]\n"]
    for i, res in enumerate(results, 1):
        formatted.append(
            f"[{i}] {res['title']}\n"
            f"URL: {res['url']}\n"
            f"Snippet: {res['snippet']}"
        )
    return "\n\n".join(formatted)

@mcp.tool()
def source_list() -> str:
    """List all ingested documents in the active workspace with basic metadata."""
    db = SessionLocal()
    try:
        docs = DocumentRepository.get_all_documents(db)
        if not docs:
            return "No documents found in workspace."
        lines = []
        for doc in docs:
            date_str = doc.published_at.strftime('%Y-%m-%d') if doc.published_at else 'unknown'
            lines.append(
                f"[{doc.id}] {doc.title}\n"
                f"  Source: {doc.source_name} ({doc.source_type or 'unknown'}) | "
                f"Date: {date_str} | Status: {doc.status or 'completed'}\n"
                f"  URL: {doc.url or 'local file'}"
            )
        return f"Total: {len(docs)} document(s)\n\n" + "\n\n".join(lines)
    except Exception as e:
        return f"source_list failed: {e}"
    finally:
        db.close()


@mcp.tool()
def source_preview(doc_id: int) -> str:
    """Preview the full cleaned text of a source document by its ID.

    Args:
        doc_id: The document ID (as shown by source_list).
    """
    db = SessionLocal()
    try:
        doc = DocumentRepository.get_document(db, doc_id)
        if not doc:
            return f"Error: No document found with ID {doc_id}."
        date_str = doc.published_at.strftime('%Y-%m-%d') if doc.published_at else 'unknown'
        header = (
            f"Document ID: {doc.id}\n"
            f"Title: {doc.title}\n"
            f"Source: {doc.source_name} ({doc.source_type or 'unknown'})\n"
            f"Author: {doc.author or 'unknown'}\n"
            f"Date: {date_str}\n"
            f"URL: {doc.url or 'local file'}\n"
            f"Trust Level: {doc.trust_level or 'medium'}\n"
            f"{'='*60}\n"
        )
        return header + doc.cleaned_text
    except Exception as e:
        return f"source_preview failed: {e}"
    finally:
        db.close()


@mcp.tool()
def retrieve(query: str, top_k: int = 10) -> str:
    """Retrieve relevant document chunks by hybrid search without LLM synthesis.

    Returns structured chunk metadata (IDs, document IDs, scores) suitable for
    programmatic agent use. Use 'ask' for LLM-synthesized answers.

    Args:
        query: The search query.
        top_k: Number of chunks to retrieve (default: 10).
    """
    db = SessionLocal()
    try:
        searcher = HybridSearcher()
        results = searcher.search(db, query, top_k=top_k)
        if not results:
            return "No matching chunks found."

        lines = [f"Retrieved {len(results)} chunk(s) for query: '{query}'\n"]
        for i, res in enumerate(results, 1):
            chunk = res["chunk"]
            doc = res["document"]
            date_str = doc.published_at.strftime('%Y-%m-%d') if doc.published_at else 'unknown'
            lines.append(
                f"[{i}] chunk_id={chunk.id} doc_id={doc.id} score={res['score']:.4f}\n"
                f"  Document: {doc.title} | {doc.source_name} | {date_str}\n"
                f"  Chunk [{chunk.chunk_index}]: {chunk.text}"
            )
        return "\n\n".join(lines)
    except Exception as e:
        return f"retrieve failed: {e}"
    finally:
        db.close()


@mcp.tool()
def graph_query(entity: str = None, relation_type: str = None, limit: int = 20) -> str:
    """Query the knowledge graph for entities and relationships.

    Args:
        entity: Filter by entity name (partial match on source or target).
        relation_type: Filter relationships by type (partial match).
        limit: Maximum number of results per category (default: 20).
    """
    db = SessionLocal()
    try:
        from softwiki.source_store.models import Entity, Relationship

        entity_q = db.query(Entity)
        if entity:
            entity_q = entity_q.filter(Entity.name.ilike(f"%{entity}%"))
        entities = entity_q.limit(limit).all()

        rel_q = db.query(Relationship)
        if entity:
            rel_q = rel_q.filter(
                (Relationship.source_name.ilike(f"%{entity}%")) |
                (Relationship.target_name.ilike(f"%{entity}%"))
            )
        if relation_type:
            rel_q = rel_q.filter(Relationship.relation_type.ilike(f"%{relation_type}%"))
        relationships = rel_q.limit(limit).all()

        if not entities and not relationships:
            return "No entities or relationships found for the given query."

        parts = []
        if entities:
            parts.append(f"Entities ({len(entities)}):")
            for e in entities:
                parts.append(f"  - [{e.type or 'unknown'}] {e.name}: {e.description or ''}")

        if relationships:
            parts.append(f"\nRelationships ({len(relationships)}):")
            for r in relationships:
                date_str = r.published_at.strftime('%Y-%m-%d') if r.published_at else 'unknown'
                parts.append(
                    f"  - {r.source_name} --[{r.relation_type}]--> {r.target_name} "
                    f"(doc_id={r.document_id}, conf={r.confidence:.2f}, date={date_str})"
                )
        return "\n".join(parts)
    except Exception as e:
        return f"graph_query failed: {e}"
    finally:
        db.close()


# ─── LightRAG tools ────────────────────────────────────────

@mcp.tool()
def lightrag_query(question: str, mode: str = "mix") -> str:
    """Query the LightRAG knowledge graph with graph traversal.

    Supports multi-hop reasoning via entity-relationship graph.
    Modes:
      - local: entity-centric, best for "what is X" questions
      - global: relation-centric, best for "what are the themes" questions
      - hybrid: both local + global (no vector chunks)
      - mix: hybrid + vector chunk retrieval (best overall)
      - naive: pure vector search (no graph)
    """
    try:
        from softwiki.graph_rag.adapter import LightRAGAdapter
        adapter = LightRAGAdapter.get_instance()
        result = adapter.sync_query(question, mode=mode)
        return str(result)
    except ImportError:
        return "LightRAG is not installed. Install with: pip install lightrag-hku"
    except Exception as e:
        return f"lightrag_query failed: {e}"


@mcp.tool()
def lightrag_explore(entity_name: str, max_depth: int = 2, max_nodes: int = 50) -> str:
    """Explore the LightRAG knowledge graph around an entity via BFS traversal.

    Args:
        entity_name: Starting entity name to explore from.
        max_depth: Maximum BFS depth (default: 2).
        max_nodes: Maximum nodes to return (default: 50).
    """
    try:
        from softwiki.graph_rag.adapter import LightRAGAdapter
        adapter = LightRAGAdapter.get_instance()
        result = adapter.sync_explore(entity_name, max_depth=max_depth, max_nodes=max_nodes)
        lines = [f"Subgraph around '{entity_name}' (depth={max_depth}):"]
        lines.append(f"  Nodes: {result['nodes_count']}, Edges: {result['edges_count']}")
        if result.get("is_truncated"):
            lines.append("  (results truncated)")
        lines.append("")
        for node in result["nodes"]:
            labels = ", ".join(node["labels"]) if node["labels"] else "unknown"
            desc = (node["properties"].get("entity_description", "") or "")[:100]
            lines.append(f"  [{labels}] {node['id']}: {desc}")
        for edge in result["edges"]:
            src = edge["source"]
            tgt = edge["target"]
            rtype = edge["properties"].get("keywords", edge.get("type", "related_to"))
            desc = (edge["properties"].get("description", "") or "")[:80]
            lines.append(f"  {src} --({rtype})--> {tgt}  {desc}")
        return "\n".join(lines)
    except ImportError:
        return "LightRAG is not installed. Install with: pip install lightrag-hku"
    except Exception as e:
        return f"lightrag_explore failed: {e}"


@mcp.tool()
def lightrag_status() -> str:
    """Get the status of the LightRAG graph engine."""
    try:
        from softwiki.graph_rag.adapter import LightRAGAdapter
        adapter = LightRAGAdapter.get_instance()
        status = adapter.sync_get_status()
        if not status.get("initialized"):
            return "LightRAG: not yet initialized (no data ingested)"
        lines = [
            "LightRAG Status:",
            f"  Working dir: {status.get('working_dir', 'N/A')}",
            f"  Graph nodes: {status.get('graph_nodes', 'N/A')}",
            f"  Graph edges: {status.get('graph_edges', 'N/A')}",
        ]
        return "\n".join(lines)
    except ImportError:
        return "LightRAG is not installed. Install with: pip install lightrag-hku"
    except Exception as e:
        return f"lightrag_status failed: {e}"


@mcp.tool()
def timeline_query(topic: str = None, start_date: str = None, end_date: str = None, limit: int = 20) -> str:
    """Query timeline events from the knowledge base in chronological order.

    Args:
        topic: Filter events by topic (partial match).
        start_date: Earliest event date, inclusive (YYYY-MM-DD).
        end_date: Latest event date, inclusive (YYYY-MM-DD).
        limit: Maximum number of events to return (default: 20).
    """
    db = SessionLocal()
    try:
        from softwiki.source_store.models import Event
        from datetime import datetime as dt

        q = db.query(Event).order_by(Event.event_date)
        if topic:
            q = q.filter(Event.topic.ilike(f"%{topic}%"))
        if start_date:
            try:
                q = q.filter(Event.event_date >= dt.fromisoformat(start_date))
            except ValueError:
                return f"Error: Invalid start_date '{start_date}'. Use YYYY-MM-DD."
        if end_date:
            try:
                q = q.filter(Event.event_date <= dt.fromisoformat(end_date))
            except ValueError:
                return f"Error: Invalid end_date '{end_date}'. Use YYYY-MM-DD."
        events = q.limit(limit).all()

        if not events:
            return "No timeline events found for the given query."

        lines = [f"Timeline Events ({len(events)}):"]
        for e in events:
            date_str = e.event_date.strftime('%Y-%m-%d') if e.event_date else 'unknown'
            lines.append(
                f"\n[{date_str}] {e.title}"
                f"\n  Topic: {e.topic or 'unknown'} | doc_id={e.document_id} | conf={e.confidence:.2f}"
                + (f"\n  {e.description}" if e.description else "")
            )
        return "\n".join(lines)
    except Exception as e:
        return f"timeline_query failed: {e}"
    finally:
        db.close()


@mcp.tool()
def claim_query(actor: str = None, topic: str = None, stance: str = None, limit: int = 20) -> str:
    """Query the claim database for source-backed assertions.

    Args:
        actor: Filter by actor name (partial match).
        topic: Filter by topic (partial match).
        stance: Filter by stance value: supportive, cautious, opposed, or unclear.
        limit: Maximum number of claims to return (default: 20).
    """
    db = SessionLocal()
    try:
        from softwiki.source_store.models import Claim

        q = db.query(Claim)
        if actor:
            q = q.filter(Claim.actor.ilike(f"%{actor}%"))
        if topic:
            q = q.filter(Claim.topic.ilike(f"%{topic}%"))
        if stance:
            q = q.filter(Claim.stance == stance)
        claims = q.limit(limit).all()

        if not claims:
            return "No claims found for the given query."

        lines = [f"Claims ({len(claims)}):"]
        for c in claims:
            date_str = c.published_at.strftime('%Y-%m-%d') if c.published_at else 'unknown'
            lines.append(
                f"\n[{c.stance.upper()}] Actor: {c.actor} | Topic: {c.topic} "
                f"| conf={c.confidence:.2f} | date={date_str} | doc_id={c.document_id}"
                f"\n  {c.text}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"claim_query failed: {e}"
    finally:
        db.close()


@mcp.tool()
def wiki_read(topic: str) -> str:
    """Read a generated wiki page by topic ID.

    Returns the markdown content of a previously compiled wiki page.
    Use wiki_build first if the page does not exist yet.

    Args:
        topic: The topic ID (e.g. 'de-dollarization').
    """
    try:
        export_dir = get_export_dir("wiki/topics")
        filepath = os.path.join(export_dir, f"{topic}.md")
        if not os.path.exists(filepath):
            return (
                f"Wiki page for '{topic}' not found. "
                f"Use wiki_build(topic='{topic}') to generate it first."
            )
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        return content
    except Exception as e:
        return f"wiki_read failed: {e}"


# Backward compatibility aliases for python imports
softwiki_status = status
softwiki_ingest = ingest
softwiki_index = index
# ── Workspace management tools ──

@mcp.tool()
def workspace_list() -> str:
    """List available workspaces and show which is active."""
    from softwiki.config import list_workspaces, get_workspace_dir
    all_ws = list_workspaces()
    active = os.path.basename(get_workspace_dir())
    lines = [f"Active: {active}", ""]
    for w in all_ws:
        mark = "→" if w == active else " "
        lines.append(f" {mark} {w}")
    return "\n".join(lines)

@mcp.tool()
def workspace_set(name: str) -> str:
    """Switch to a different workspace.
    Args:
        name: Workspace directory name (e.g. 'eva-kb', 'default').
    """
    from softwiki.config import set_workspace_dir
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ws_path = os.path.join(project_root, "..", "workspace", name)
    ws_path = os.path.abspath(ws_path)
    if not os.path.isdir(os.path.join(ws_path, ".softwiki")):
        return f"Workspace '{name}' not found or not initialized."
    set_workspace_dir(ws_path)
    return f"Switched to '{name}'. Active: {os.path.basename(get_workspace_dir())}"

# ── Module management tools ──

@mcp.tool()
def modules_list() -> str:
    """List all knowledge modules and their enabled/disabled status."""
    from softwiki.config import get_enabled_modules, is_module_enabled, get_workspace_dir
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
        enabled: Comma-separated list of module names to enable (e.g. "rag,graph,claimdb").
                 Modules not in the list will be disabled. Valid names: rag, graph, claimdb, timeline, llmwiki.
        scope: "global" — runtime (resets on restart), "workspace" — persisted for this workspace.
    """
    from softwiki.config import set_enabled_modules, set_workspace_modules
    valid = {"rag", "graph", "claimdb", "timeline", "llmwiki"}
    modules = [m.strip().lower() for m in enabled.split(",") if m.strip().lower() in valid]
    if scope == "workspace":
        set_workspace_modules(modules)
    else:
        set_enabled_modules(modules)
    return modules_list()

softwiki_wiki_build = wiki_build
softwiki_web_search = web_search
softwiki_source_list = source_list
softwiki_source_preview = source_preview
softwiki_retrieve = retrieve
softwiki_graph_query = graph_query
softwiki_lightrag_query = lightrag_query
softwiki_lightrag_explore = lightrag_explore
softwiki_lightrag_status = lightrag_status
softwiki_timeline_query = timeline_query
softwiki_claim_query = claim_query
softwiki_wiki_read = wiki_read

if __name__ == "__main__":
    mcp.run()
