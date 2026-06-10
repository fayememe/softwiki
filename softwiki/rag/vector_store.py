import os
import numpy as np
from typing import List, Dict, Any
from softwiki.config import get_index_path

class LocalVectorStore:
    def __init__(self):
        # We will dynamically reload if the workspace changes
        self.last_loaded_path = None
        self.chunk_ids = []
        self.embeddings = []
        self.load()

    def get_current_path(self) -> str:
        return get_index_path("vector_index.npz")

    def load(self):
        current_path = self.get_current_path()
        if os.path.exists(current_path):
            try:
                data = np.load(current_path, allow_pickle=True)
                self.chunk_ids = list(data["chunk_ids"])
                self.embeddings = data["embeddings"].tolist()
                self.last_loaded_path = current_path
            except Exception as e:
                print(f"Error loading vector index at {current_path}: {e}. Starting fresh.")
                self.chunk_ids = []
                self.embeddings = []
                self.last_loaded_path = current_path
        else:
            self.chunk_ids = []
            self.embeddings = []
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
            embeddings=np.array(self.embeddings)
        )
        self.last_loaded_path = current_path

    def add_vectors(self, chunk_ids: List[int], embeddings: List[List[float]]):
        self._ensure_correct_index_loaded()
        id_to_idx = {cid: idx for idx, cid in enumerate(self.chunk_ids)}
        
        for cid, emb in zip(chunk_ids, embeddings):
            if cid in id_to_idx:
                self.embeddings[id_to_idx[cid]] = emb
            else:
                self.chunk_ids.append(cid)
                self.embeddings.append(emb)
        self.save()

    def delete_vectors(self, chunk_ids: List[int]):
        self._ensure_correct_index_loaded()
        cids_to_del = set(chunk_ids)
        new_chunk_ids = []
        new_embeddings = []
        for cid, emb in zip(self.chunk_ids, self.embeddings):
            if cid not in cids_to_del:
                new_chunk_ids.append(cid)
                new_embeddings.append(emb)
        self.chunk_ids = new_chunk_ids
        self.embeddings = new_embeddings
        self.save()

    def search(self, query_vector: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        self._ensure_correct_index_loaded()
        if not self.embeddings:
            return []

        q_vec = np.array(query_vector)
        embs = np.array(self.embeddings)
        
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
