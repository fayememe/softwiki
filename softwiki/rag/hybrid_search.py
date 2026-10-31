import os
import re
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from softwiki.rag.vector_store import LocalVectorStore
from softwiki.rag.bm25_store import Bm25Store
from softwiki.rag.embedder import WikiEmbedder
from softwiki.source_store.document_repo import DocumentRepository

class HybridSearcher:
    def __init__(self):
        self.vector_store = LocalVectorStore()
        self.bm25_store = Bm25Store()
        self.embedder = WikiEmbedder()

    def search(self, db: Session, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        query_vector = self.embedder.embed_query(query)
        vector_results = self.vector_store.search(query_vector, top_k=top_k * 2)
        bm25_results = self.bm25_store.search(query, top_k=top_k * 2)

        rrf_scores = {}
        constant = 60
        
        for rank, res in enumerate(vector_results):
            cid = res["chunk_id"]
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (constant + rank + 1)
            
        for rank, res in enumerate(bm25_results):
            cid = res["chunk_id"]
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (constant + rank + 1)

        # Fetch extra candidates so exact/normalized duplicate chunks can be
        # collapsed without starving the final top_k.
        sorted_chunks = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:top_k * 2]

        if not sorted_chunks:
            return []

        candidate_ids = [cid for cid, _ in sorted_chunks]
        fetched = DocumentRepository.get_chunks_by_ids(db, candidate_ids)
        chunk_map = {c.id: c for c in fetched}

        candidates = []
        seen = set()
        for cid, score in sorted_chunks:
            chunk = chunk_map.get(cid)
            if not chunk:
                continue
            normalized = re.sub(r"\s+", " ", (chunk.text or "").lower()).strip()
            key = (chunk.document_id, normalized)
            if key in seen:
                continue
            seen.add(key)
            doc = DocumentRepository.get_document(db, chunk.document_id)
            candidates.append({"chunk": chunk, "document": doc, "score": score})

        # Lightweight MMR: keep relevance but penalize near-duplicate context.
        if len(candidates) <= 1:
            return candidates[:top_k]
        lam = float(os.getenv("RAG_MMR_LAMBDA", "0.3"))
        selected = []
        remaining = list(candidates)
        token_cache = {}

        def toks(text):
            key = id(text)
            if key not in token_cache:
                token_cache[key] = set(re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", (text or "").lower()))
            return token_cache[key]

        while remaining and len(selected) < top_k:
            best = None
            best_score = -1e9
            for cand in remaining:
                rel = cand["score"]
                if selected:
                    sim = max(
                        (len(toks(cand["chunk"].text) & toks(s["chunk"].text)) /
                         max(1, len(toks(cand["chunk"].text) | toks(s["chunk"].text))))
                        for s in selected
                    )
                else:
                    sim = 0.0
                mmr = rel - lam * sim
                if mmr > best_score:
                    best, best_score = cand, mmr
            selected.append(best)
            remaining.remove(best)
        return selected
