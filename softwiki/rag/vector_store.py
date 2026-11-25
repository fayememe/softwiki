import os
import numpy as np
from typing import List, Dict, Any
from softwiki.config import get_index_path

_VECTOR_CACHE = {}


class FileVectorStore:
    """Legacy backend: one .npz per workspace, brute-force cosine."""

    def __init__(self):
        self.last_loaded_path = None
        self.chunk_ids = []
        self.embeddings = np.empty((0, 0), dtype=np.float64)
        self.load()

    def get_current_path(self) -> str:
        return get_index_path("vector_index.npz")

    def load(self):
        current_path = self.get_current_path()
        cached = _VECTOR_CACHE.get(current_path)
        if cached is not None:
            self.chunk_ids, self.embeddings = cached
            self.last_loaded_path = current_path
            return
        if os.path.exists(current_path):
            try:
                data = np.load(current_path, allow_pickle=True)
                self.chunk_ids = list(data["chunk_ids"])
                self.embeddings = np.asarray(data["embeddings"], dtype=np.float64)
                _VECTOR_CACHE[current_path] = (self.chunk_ids, self.embeddings)
                self.last_loaded_path = current_path
            except Exception as e:
                print(f"Error loading vector index at {current_path}: {e}. Starting fresh.")
                self.chunk_ids = []
                self.embeddings = np.empty((0, 0), dtype=np.float64)
                self.last_loaded_path = current_path
        else:
            self.chunk_ids = []
            self.embeddings = np.empty((0, 0), dtype=np.float64)
            self.last_loaded_path = current_path

    def _ensure_correct_index_loaded(self):
        """Reloads the index if the active workspace path has changed."""
        if self.get_current_path() != self.last_loaded_path:
            self.load()

    def reset(self):
        current_path = self.get_current_path()
        self.chunk_ids = []
        self.embeddings = np.empty((0, 0), dtype=np.float64)
        _VECTOR_CACHE.pop(current_path, None)
        self.last_loaded_path = current_path

    def save(self):
        self._ensure_correct_index_loaded()
        if not self.chunk_ids:
            return
        current_path = self.get_current_path()
        os.makedirs(os.path.dirname(current_path), exist_ok=True)
        np.savez(
            current_path,
            chunk_ids=np.array(self.chunk_ids),
            embeddings=self.embeddings
        )
        _VECTOR_CACHE[current_path] = (self.chunk_ids, self.embeddings)
        self.last_loaded_path = current_path

    def add_vectors(self, chunk_ids: List[int], embeddings: List[List[float]]):
        self._ensure_correct_index_loaded()
        id_to_idx = {cid: idx for idx, cid in enumerate(self.chunk_ids)}
        new_ids = []
        new_rows = []

        for cid, emb in zip(chunk_ids, embeddings):
            if cid in id_to_idx:
                self.embeddings[id_to_idx[cid]] = emb
            else:
                new_ids.append(cid)
                new_rows.append(emb)

        if new_rows:
            dtype = self.embeddings.dtype if self.embeddings.size else np.float64
            rows = np.asarray(new_rows, dtype=dtype)
            if self.embeddings.size:
                self.embeddings = np.vstack([self.embeddings, rows])
            else:
                self.embeddings = rows
            self.chunk_ids.extend(new_ids)
        self.save()

    def delete_vectors(self, chunk_ids: List[int]):
        self._ensure_correct_index_loaded()
        cids_to_del = set(chunk_ids)
        keep = [i for i, cid in enumerate(self.chunk_ids) if cid not in cids_to_del]
        self.chunk_ids = [self.chunk_ids[i] for i in keep]
        if self.embeddings.size:
            self.embeddings = self.embeddings[keep]
        self.save()

    def search(self, query_vector: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        self._ensure_correct_index_loaded()
        if self.embeddings.size == 0:
            return []

        q_vec = np.asarray(query_vector, dtype=self.embeddings.dtype)
        embs = self.embeddings
        if embs.ndim != 2 or q_vec.shape[0] != embs.shape[1]:
            print(
                f"Embedding dimension mismatch: query {q_vec.shape}, index {embs.shape}"
            )
            return []

        q_norm = np.linalg.norm(q_vec)
        emb_norms = np.linalg.norm(embs, axis=1)
        
        if q_norm == 0:
            return []
            
        emb_norms[emb_norms == 0] = 1e-10
        similarities = np.dot(embs, q_vec) / (emb_norms * q_norm)
        
        top_indices = np.argsort(similarities)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            results.append({
                "chunk_id": int(self.chunk_ids[idx]),
                "score": float(similarities[idx])
            })
            
        return results


class PgVectorStore:
    """PostgreSQL + pgvector backend.

    Same interface as ``FileVectorStore`` so callers (hybrid search, /api/index,
    MCP) do not change. One database per knowledge base means no kb column is
    needed; chunk ids are stable and cascaded on chunk deletion.
    """

    _ensured_urls: set[str] = set()

    def __init__(self):
        self.last_loaded_path = None
        self._dim = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))
        self._model = os.getenv("EMBEDDING_MODEL", "unknown")

    # ── connection / schema ──
    def _session(self):
        from softwiki.source_store.db import SessionLocal
        return SessionLocal()

    def _url(self) -> str:
        from softwiki.config import get_db_url
        return get_db_url()

    def _ensure_schema(self, db) -> None:
        url = str(db.get_bind().url)
        if url in self._ensured_urls:
            return
        from sqlalchemy import text
        db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        db.execute(text(
            "CREATE TABLE IF NOT EXISTS chunk_embeddings ("
            " chunk_id BIGINT PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,"
            " model TEXT NOT NULL DEFAULT '',"
            " dim INTEGER NOT NULL DEFAULT 0,"
            f" embedding vector({self._dim}) NOT NULL)"
        ))
        db.commit()
        self._ensured_urls.add(url)

    # ── interface ──
    def get_current_path(self) -> str:
        return f"pgvector://{self._url()}#chunk_embeddings"

    def load(self):
        return None

    def save(self):
        return None

    def reset(self):
        from sqlalchemy import text
        db = self._session()
        try:
            self._ensure_schema(db)
            db.execute(text("TRUNCATE TABLE chunk_embeddings"))
            db.commit()
        finally:
            db.close()

    def add_vectors(self, chunk_ids: List[int], embeddings: List[List[float]]):
        if not chunk_ids:
            return
        from sqlalchemy import bindparam, text
        db = self._session()
        try:
            self._ensure_schema(db)
            rows = []
            for chunk_id, vector in zip(chunk_ids, embeddings):
                vec = np.asarray(vector, dtype=np.float32)
                if vec.ndim != 1 or vec.size == 0:
                    continue
                if vec.size != self._dim:
                    self._dim = int(vec.size)
                rows.append({
                    "chunk_id": int(chunk_id),
                    "vec": "[" + ",".join(f"{v:.7g}" for v in vec) + "]",
                })
            if not rows:
                return
            stmt = text(
                "INSERT INTO chunk_embeddings (chunk_id, model, dim, embedding)"
                " VALUES (:chunk_id, :model, :dim, CAST(:vec AS vector))"
                " ON CONFLICT (chunk_id) DO UPDATE"
                " SET embedding = EXCLUDED.embedding, model = EXCLUDED.model, dim = EXCLUDED.dim"
            ).bindparams(bindparam("model", value=self._model), bindparam("dim", value=self._dim))
            db.execute(stmt, rows)
            db.commit()
        finally:
            db.close()

    def delete_vectors(self, chunk_ids: List[int]):
        if not chunk_ids:
            return
        from sqlalchemy import text
        db = self._session()
        try:
            self._ensure_schema(db)
            db.execute(
                text("DELETE FROM chunk_embeddings WHERE chunk_id = ANY(:ids)"),
                {"ids": [int(cid) for cid in chunk_ids]},
            )
            db.commit()
        finally:
            db.close()

    def search(self, query_vector: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        from sqlalchemy import text
        vec = np.asarray(query_vector, dtype=np.float32)
        if vec.ndim != 1 or vec.size == 0:
            return []
        literal = "[" + ",".join(f"{v:.7g}" for v in vec) + "]"
        db = self._session()
        try:
            self._ensure_schema(db)
            # HNSW prunes by ef_search; it must be >= the requested k or the
            # index returns fewer/less accurate neighbours.
            ef_search = max(40, int(top_k) * 4)
            db.execute(text(f"SET LOCAL hnsw.ef_search = {ef_search}"))
            # The planner mis-prices HNSW vs a 1.5k-dim seq scan on 40k rows and
            # picks the latter (~400 ms). Force the ANN index for this query.
            db.execute(text("SET LOCAL enable_seqscan = off"))
            rows = db.execute(
                text(
                    "SELECT chunk_id, 1 - (embedding <=> CAST(:q AS vector)) AS score"
                    " FROM chunk_embeddings"
                    " ORDER BY embedding <=> CAST(:q AS vector)"
                    " LIMIT :k"
                ),
                {"q": literal, "k": max(1, int(top_k))},
            ).all()
            return [
                {"chunk_id": int(row[0]), "score": float(row[1])}
                for row in rows
            ]
        finally:
            db.close()


class LocalVectorStore:
    """Facade: file backend by default, pgvector when enabled.

    All existing call sites instantiate ``LocalVectorStore()``; the backend is
    chosen here so the migration is a single environment switch:
    ``SOFTWIKI_VECTOR_BACKEND=pg``.
    """

    def __new__(cls, *args, **kwargs):
        backend = (os.getenv("SOFTWIKI_VECTOR_BACKEND") or "file").strip().lower()
        if backend in ("pg", "postgres", "postgresql", "pgvector"):
            return PgVectorStore(*args, **kwargs)
        return FileVectorStore(*args, **kwargs)
