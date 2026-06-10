import os
import pickle
import re
from typing import List, Dict, Any
from rank_bm25 import BM25Okapi
from softwiki.config import get_index_path

def tokenize(text: str) -> List[str]:
    if not text:
        return []
    
    text = text.lower()
    tokens = []
    
    pattern = re.compile(r'([\u4e00-\u9fff]|[a-zA-Z0-9]+)')
    
    for match in pattern.finditer(text):
        token = match.group(1)
        if re.match(r'[\u4e00-\u9fff]', token):
            tokens.append(token)
        else:
            tokens.append(token)
            
    return tokens

class Bm25Store:
    def __init__(self):
        self.last_loaded_path = None
        self.chunk_ids = []
        self.corpus_texts = []
        self.bm25 = None
        self.load()

    def get_current_path(self) -> str:
        return get_index_path("bm25_index.pkl")

    def load(self):
        current_path = self.get_current_path()
        if os.path.exists(current_path):
            try:
                with open(current_path, "rb") as f:
                    data = pickle.load(f)
                    self.chunk_ids = data["chunk_ids"]
                    self.corpus_texts = data["corpus_texts"]
                if self.corpus_texts:
                    tokenized_corpus = [tokenize(t) for t in self.corpus_texts]
                    self.bm25 = BM25Okapi(tokenized_corpus)
                self.last_loaded_path = current_path
            except Exception as e:
                print(f"Error loading BM25 index at {current_path}: {e}. Starting fresh.")
                self.chunk_ids = []
                self.corpus_texts = []
                self.bm25 = None
                self.last_loaded_path = current_path
        else:
            self.chunk_ids = []
            self.corpus_texts = []
            self.bm25 = None
            self.last_loaded_path = current_path

    def _ensure_correct_index_loaded(self):
        if self.get_current_path() != self.last_loaded_path:
            self.load()

    def save(self):
        self._ensure_correct_index_loaded()
        current_path = self.get_current_path()
        os.makedirs(os.path.dirname(current_path), exist_ok=True)
        with open(current_path, "wb") as f:
            pickle.dump({
                "chunk_ids": self.chunk_ids,
                "corpus_texts": self.corpus_texts
            }, f)
        self.last_loaded_path = current_path

    def add_documents(self, chunk_id_to_text: Dict[int, str]):
        """Incrementally add new chunks and rebuild BM25 (BM25 requires full corpus for IDF)."""
        self._ensure_correct_index_loaded()
        existing_ids = set(self.chunk_ids)
        for cid, text in chunk_id_to_text.items():
            if cid not in existing_ids:
                self.chunk_ids.append(cid)
                self.corpus_texts.append(text)
        if self.corpus_texts:
            tokenized_corpus = [tokenize(t) for t in self.corpus_texts]
            self.bm25 = BM25Okapi(tokenized_corpus)
        self.save()

    def rebuild_index(self, chunk_id_to_text: Dict[int, str]):
        self.chunk_ids = list(chunk_id_to_text.keys())
        self.corpus_texts = [chunk_id_to_text[cid] for cid in self.chunk_ids]
        
        if self.corpus_texts:
            tokenized_corpus = [tokenize(t) for t in self.corpus_texts]
            self.bm25 = BM25Okapi(tokenized_corpus)
        else:
            self.bm25 = None
            
        self.save()

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        self._ensure_correct_index_loaded()
        if not self.bm25 or not self.chunk_ids:
            return []

        tokenized_query = tokenize(query)
        scores = self.bm25.get_scores(tokenized_query)
        
        import numpy as np
        top_indices = np.argsort(scores)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            score = float(scores[idx])
            if score > 0:
                results.append({
                    "chunk_id": int(self.chunk_ids[idx]),
                    "score": score
                })
                
        return results
