"""
LightRAG adapter for SoftWiki.

Runs alongside the existing SQLite-based graph pipeline, providing:
- Incremental graph insertion via LLM extraction
- Multi-mode graph querying (local/global/hybrid/mix)
- Subgraph exploration (BFS traversal)

LightRAG uses its own independent storage (JSON/NetworkX/NanoVectorDB),
separate from SoftWiki's SQLite.
"""

import os
import asyncio
import logging
import numpy as np
from typing import Optional

from lightrag import LightRAG, QueryParam
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc

from softwiki.config import get_softwiki_dir

logger = logging.getLogger(__name__)


# ─── Separated config: LLM and Embedding can use different providers ───
#
# LLM (entity extraction + query synthesis):
#   LIGHTRAG_LLM_API_KEY   → fallback OPENAI_API_KEY
#   LIGHTRAG_LLM_API_BASE  → fallback OPENAI_API_BASE
#   LIGHTRAG_LLM_MODEL     → fallback EXTRACTION_MODEL → "gpt-4o-mini"
#
# Embedding (vector index):
#   LIGHTRAG_EMBED_API_KEY   → fallback OPENAI_API_KEY
#   LIGHTRAG_EMBED_API_BASE  → fallback OPENAI_API_BASE
#   LIGHTRAG_EMBED_MODEL     → fallback EMBEDDING_MODEL → "text-embedding-3-small"
#   LIGHTRAG_EMBED_PROVIDER  → fallback EMBEDDING_PROVIDER → "openai"
#   LIGHTRAG_EMBED_DIM       → fallback auto-detect (see KNOWN_EMBED_DIMS)
#
# Storage backend:
#   LIGHTRAG_STORAGE          → "json" (default, zero-config) | "postgres"
#   LIGHTRAG_PG_URL           → PostgreSQL connection string (when storage=postgres)


KNOWN_EMBED_DIMS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
    "text-embedding-004": 768,
    "models/embedding-001": 768,
    "deepseek-embedding": 2048,
    "bge-m3": 1024,
    "bge-small-zh-v1.5": 512,
    "all-MiniLM-L6-v2": 384,
}


def _resolve(key: str, *fallbacks: str) -> str:
    """Resolve env var: try key, then each fallback in order."""
    for k in (key, *fallbacks):
        v = os.getenv(k)
        if v:
            return v
    return ""


def _llm_config() -> dict:
    return {
        "api_key": _resolve("LIGHTRAG_LLM_API_KEY", "OPENAI_API_KEY"),
        "base_url": _resolve("LIGHTRAG_LLM_API_BASE", "OPENAI_API_BASE") or "https://api.openai.com/v1",
        "model": _resolve("LIGHTRAG_LLM_MODEL", "EXTRACTION_MODEL") or "gpt-4o-mini",
    }


def _embed_config() -> dict:
    provider = _resolve("LIGHTRAG_EMBED_PROVIDER", "EMBEDDING_PROVIDER") or "openai"
    model = _resolve("LIGHTRAG_EMBED_MODEL", "EMBEDDING_MODEL") or "text-embedding-3-small"
    dim = os.getenv("LIGHTRAG_EMBED_DIM")
    if not dim:
        dim = str(KNOWN_EMBED_DIMS.get(model, 1536))
    return {
        "provider": provider,
        "api_key": _resolve("LIGHTRAG_EMBED_API_KEY", "OPENAI_API_KEY"),
        "base_url": _resolve("LIGHTRAG_EMBED_API_BASE", "OPENAI_API_BASE") or "https://api.openai.com/v1",
        "model": model,
        "dim": int(dim),
    }


def _storage_config() -> dict:
    """Resolve storage backend config."""
    backend = (os.getenv("LIGHTRAG_STORAGE") or "json").lower()
    cfg = {"backend": backend}
    if backend == "postgres":
        cfg["pg_url"] = os.getenv("LIGHTRAG_PG_URL", "postgresql://localhost:5432/softwiki")
    return cfg


def has_lightrag_credentials() -> bool:
    """Check if enough credentials exist to run LightRAG (LLM + embedding)."""
    llm = _llm_config()
    emb = _embed_config()
    llm_ok = bool(llm["api_key"]) and not llm["api_key"].startswith("your_")
    emb_ok = bool(emb["api_key"]) and not emb["api_key"].startswith("your_") or emb["provider"] == "local"
    return llm_ok and emb_ok


async def _llm_model_func(
    prompt: str,
    system_prompt: Optional[str] = None,
    history_messages: Optional[list] = None,
    **kwargs,
) -> str:
    """Call LLM via LIGHTRAG_LLM_* or fallback OPENAI_* config."""
    cfg = _llm_config()
    return await openai_complete_if_cache(
        cfg["model"],
        prompt,
        system_prompt=system_prompt,
        history_messages=history_messages,
        api_key=cfg["api_key"],
        base_url=cfg["base_url"],
        **kwargs,
    )


# ─── Embedding function: dynamic dimension from config ───

async def _embed_raw(texts: list[str], embed_cfg: dict) -> np.ndarray:
    """Raw embedding call, given pre-resolved config."""
    if embed_cfg["provider"] == "local":
        dim = embed_cfg["dim"]
        embeds = np.zeros((len(texts), dim), dtype=np.float32)
        for i, t in enumerate(texts):
            chars = np.frombuffer(t.encode("utf-32", "replace"), dtype=np.uint32)[1:] % dim
            if len(chars) > 0:
                embeds[i] = np.bincount(chars, minlength=dim).astype(np.float32)
            embeds[i] = embeds[i] / (np.linalg.norm(embeds[i]) + 1e-12)
        return embeds
    return await openai_embed(
        texts,
        model=embed_cfg["model"],
        api_key=embed_cfg["api_key"],
        base_url=embed_cfg["base_url"],
    )


def _make_embedding_func() -> EmbeddingFunc:
    """Build an EmbeddingFunc with dimension from current config."""
    cfg = _embed_config()

    async def _embed(texts: list[str]) -> np.ndarray:
        return await _embed_raw(texts, cfg)

    return EmbeddingFunc(
        embedding_dim=cfg["dim"],
        func=_embed,
        max_token_size=8192,
        model_name=cfg["model"],
        send_dimensions=False,
        supports_asymmetric=False,
    )


# ─── Dimension safety check ───

def _detect_stored_dim(working_dir: str) -> Optional[int]:
    """Read embedding dimension from an existing NanoVectorDB storage file."""
    for fname in ("vdb_entities.json", "vdb_relationships.json", "vdb_chunks.json"):
        path = os.path.join(working_dir, fname)
        if os.path.exists(path):
            try:
                import json
                with open(path, "r") as f:
                    data = json.load(f)
                # NanoVectorDB stores embedding_dim at top level
                dim = data.get("embedding_dim")
                if dim:
                    return int(dim)
            except Exception:
                continue
    return None


def _check_dimension_mismatch(working_dir: str, config_dim: int, model_name: str):
    """Warn loudly if the stored embedding dimension differs from the current config.

    When the embedding model changes, dimensions can differ.  The user must
    explicitly delete the LightRAG storage directory to rebuild, or revert the
    config change.  Never auto-rebuild.
    """
    graphml = os.path.join(working_dir, "graph_chunk_entity_relation.graphml")
    if not os.path.exists(graphml):
        return  # fresh workspace, nothing to check

    stored_dim = _detect_stored_dim(working_dir)
    if stored_dim is None:
        return  # can't determine stored dim, skip check

    if stored_dim != config_dim:
        lr_dir = working_dir
        msg = (
            f"\n"
            f"╔══════════════════════════════════════════════════════════════╗\n"
            f"║  EMBEDDING MODEL DIMENSION MISMATCH                        ║\n"
            f"╠══════════════════════════════════════════════════════════════╣\n"
            f"║  Stored dimension : {stored_dim:<5d}                                ║\n"
            f"║  Config dimension : {config_dim:<5d}  ({model_name})            ║\n"
            f"║                                                              ║\n"
            f"║  The embedding model has changed.  LightRAG cannot continue  ║\n"
            f"║  because the existing vector index is locked to the old      ║\n"
            f"║  dimension.                                                  ║\n"
            f"║                                                              ║\n"
            f"║  To fix, choose ONE of:                                      ║\n"
            f"║  1. Delete this directory and re-ingest ALL documents:       ║\n"
            f"║       rm -rf {lr_dir:<55s}  ║\n"
            f"║  2. Revert the embedding config to the previous settings.    ║\n"
            f"╚══════════════════════════════════════════════════════════════╝"
        )
        logger.error(msg)
        raise RuntimeError(
            f"Embedding dimension mismatch: stored={stored_dim}, "
            f"config={config_dim} ({model_name}). "
            f"Delete '{lr_dir}' and re-ingest, or revert config."
        )


# ─── LightRAG Wrapper ───

class LightRAGAdapter:
    """Singleton-ish wrapper around LightRAG for SoftWiki integration.

    Usage:
        adapter = LightRAGAdapter.get_instance(workspace_dir)
        # Insert
        await adapter.insert_text("document text...")
        # Query
        result = await adapter.query("question", mode="mix")
        # Explore subgraph
        graph = await adapter.explore("EntityName", max_depth=2)
    """

    _instances: dict[str, "LightRAGAdapter"] = {}

    def __init__(self, workspace_dir: str):
        self._workspace = workspace_dir
        self._rag: Optional[LightRAG] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._initialized = False

    @classmethod
    def get_instance(cls, workspace_dir: Optional[str] = None) -> "LightRAGAdapter":
        """Get or create a LightRAGAdapter for the given workspace."""
        from softwiki.config import get_workspace_dir
        ws = workspace_dir or get_workspace_dir()
        ws_abs = os.path.abspath(ws)
        if ws_abs not in cls._instances:
            cls._instances[ws_abs] = LightRAGAdapter(ws_abs)
        return cls._instances[ws_abs]

    @property
    def _working_dir(self) -> str:
        """LightRAG storage directory inside the workspace."""
        return get_softwiki_dir("lightrag")

    async def initialize(self):
        """Set up LightRAG storage directories and initialize the engine."""
        if self._initialized:
            return

        wd = self._working_dir
        os.makedirs(wd, exist_ok=True)

        # ── Dimension safety check ──
        embed_cfg = _embed_config()
        _check_dimension_mismatch(wd, embed_cfg["dim"], embed_cfg["model"])

        logger.info(f"Initializing LightRAG at {wd} (embed_dim={embed_cfg['dim']})")
        llm_cfg = _llm_config()
        store_cfg = _storage_config()

        # Resolve storage backends: json (default) or postgres
        if store_cfg["backend"] == "postgres":
            from lightrag.kg.postgres_impl import PGKVStorage, PGVectorStorage, PGGraphStorage, PGDocStatusStorage
            kv_storage = PGKVStorage
            vector_storage = PGVectorStorage
            graph_storage = PGGraphStorage
            doc_status_storage = PGDocStatusStorage
            log_msg = f"PostgreSQL ({store_cfg['pg_url']})"
        else:
            kv_storage = "JsonKVStorage"
            vector_storage = "NanoVectorDBStorage"
            graph_storage = "NetworkXStorage"
            doc_status_storage = "JsonDocStatusStorage"
            log_msg = "JSON files (default)"

        logger.info(f"LightRAG storage backend: {log_msg}")

        kwargs = dict(
            working_dir=wd,
            llm_model_func=_llm_model_func,
            embedding_func=_make_embedding_func(),
            llm_model_name=llm_cfg["model"],
            kv_storage=kv_storage,
            vector_storage=vector_storage,
            graph_storage=graph_storage,
            doc_status_storage=doc_status_storage,
            enable_llm_cache=True,
            enable_llm_cache_for_entity_extract=True,
            entity_extraction_use_json=True,
            chunk_token_size=1200,
            chunk_overlap_token_size=100,
            top_k=40,
            max_entity_tokens=6000,
            max_relation_tokens=8000,
            max_total_tokens=30000,
            addon_params={"language": "English"},
        )

        if store_cfg["backend"] == "postgres":
            kwargs["db_url"] = store_cfg["pg_url"]

        self._rag = LightRAG(**kwargs)
        await self._rag.initialize_storages()
        self._initialized = True
        logger.info("LightRAG initialized successfully")

    async def insert_text(self, text: str, source_id: Optional[str] = None) -> dict:
        """Insert document text into LightRAG.

        LightRAG will automatically:
        1. Chunk the text
        2. Extract entities and relations via LLM
        3. Compute embeddings
        4. Store in its graph + vector indices
        """
        if not self._initialized:
            await self.initialize()

        assert self._rag is not None
        logger.info(f"Inserting text ({len(text)} chars) into LightRAG")

        # Prepend source context if available
        insert_text = text
        if source_id:
            insert_text = f"[Source: {source_id}]\n{text}"

        await self._rag.ainsert(insert_text)
        logger.info("LightRAG insert complete")
        return {"status": "inserted", "length": len(insert_text)}

    async def query(self, question: str, mode: str = "mix", top_k: int = 40) -> str:
        """Query LightRAG's knowledge graph.

        Args:
            question: The user's question
            mode: Query mode — "local", "global", "hybrid", "mix", or "naive"
            top_k: Number of entities/relations to retrieve

        Returns:
            LLM-synthesized answer string
        """
        if not self._initialized:
            await self.initialize()

        assert self._rag is not None

        param = QueryParam(mode=mode, top_k=top_k)
        result = await self._rag.aquery(question, param=param)
        return str(result)

    async def query_context(self, question: str, mode: str = "mix", top_k: int = 40) -> str:
        """Get raw retrieved context without LLM synthesis."""
        if not self._initialized:
            await self.initialize()

        assert self._rag is not None

        param = QueryParam(mode=mode, top_k=top_k, only_need_context=True)
        result = await self._rag.aquery(question, param=param)
        return str(result)

    async def explore(
        self, entity_name: str, max_depth: int = 2, max_nodes: int = 50
    ) -> dict:
        """Explore the subgraph around an entity via BFS traversal.

        Returns dict with nodes and edges.
        """
        if not self._initialized:
            await self.initialize()

        assert self._rag is not None

        kg = await self._rag.graph_storage.get_knowledge_graph(
            entity_name, max_depth=max_depth, max_nodes=max_nodes
        )

        nodes = []
        for node in kg.nodes:
            nodes.append({
                "id": node.id,
                "labels": node.labels,
                "properties": node.properties,
            })

        edges = []
        for edge in kg.edges:
            edges.append({
                "id": edge.id,
                "type": edge.type,
                "source": edge.source,
                "target": edge.target,
                "properties": edge.properties,
            })

        return {
            "entity": entity_name,
            "max_depth": max_depth,
            "nodes_count": len(nodes),
            "edges_count": len(edges),
            "nodes": nodes,
            "edges": edges,
            "is_truncated": getattr(kg, "is_truncated", False),
        }

    async def get_status(self) -> dict:
        """Get LightRAG storage status."""
        if not self._initialized:
            return {"initialized": False}

        assert self._rag is not None
        wd = self._working_dir

        status = {"initialized": True, "working_dir": wd}

        # Count graph nodes from NetworkX
        try:
            graph = self._rag.graph_storage
            node_count = len(graph._graph.nodes) if hasattr(graph, "_graph") else 0
            edge_count = len(graph._graph.edges) if hasattr(graph, "_graph") else 0
            status["graph_nodes"] = node_count
            status["graph_edges"] = edge_count
        except Exception as e:
            status["graph_error"] = str(e)

        return status

    # ─── Sync helpers (for non-async contexts like MCP tools) ───

    def _ensure_loop(self):
        """Get or create an event loop for sync wrappers."""
        try:
            self._loop = asyncio.get_running_loop()
            # We're already in an async context — use it directly
            return self._loop
        except RuntimeError:
            # No running loop — create one
            if self._loop is None or self._loop.is_closed():
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
            return self._loop

    def sync_insert_text(self, text: str, source_id: Optional[str] = None) -> dict:
        """Sync wrapper for insert_text."""
        loop = self._ensure_loop()
        return loop.run_until_complete(self.insert_text(text, source_id))

    def sync_query(self, question: str, mode: str = "mix", top_k: int = 40) -> str:
        """Sync wrapper for query."""
        loop = self._ensure_loop()
        return loop.run_until_complete(self.query(question, mode, top_k))

    def sync_query_context(self, question: str, mode: str = "mix", top_k: int = 40) -> str:
        """Sync wrapper for query_context."""
        loop = self._ensure_loop()
        return loop.run_until_complete(self.query_context(question, mode, top_k))

    def sync_explore(self, entity_name: str, max_depth: int = 2, max_nodes: int = 50) -> dict:
        """Sync wrapper for explore."""
        loop = self._ensure_loop()
        return loop.run_until_complete(self.explore(entity_name, max_depth, max_nodes))

    def sync_get_status(self) -> dict:
        """Sync wrapper for get_status."""
        loop = self._ensure_loop()
        return loop.run_until_complete(self.get_status())

    def close(self):
        """Cleanup."""
        if self._loop and not self._loop.is_closed():
            self._loop.close()
        self._initialized = False
        self._rag = None


# ─── Module-level helpers for easy import ───

def get_adapter(workspace_dir: Optional[str] = None) -> LightRAGAdapter:
    """Convenience: get or create the adapter for the active workspace."""
    return LightRAGAdapter.get_instance(workspace_dir)
