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

        sorted_chunks = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

        if not sorted_chunks:
            return []

        candidate_ids = [cid for cid, _ in sorted_chunks]
        fetched = DocumentRepository.get_chunks_by_ids(db, candidate_ids)
        chunk_map = {c.id: c for c in fetched}

        results = []
        for cid, score in sorted_chunks:
            chunk = chunk_map.get(cid)
            if chunk:
                doc = DocumentRepository.get_document(db, chunk.document_id)
                results.append({"chunk": chunk, "document": doc, "score": score})

        return results
