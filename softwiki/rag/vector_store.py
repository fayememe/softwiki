import os
import numpy as np
from typing import List, Dict, Any
from softwiki.config import get_index_path

_VECTOR_CACHE = {}


class LocalVectorStore:
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
