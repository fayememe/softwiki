import os
import time
import threading
import numpy as np
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List

_openai_client = None
_local_model = None


class _TokenRateLimiter:
    def __init__(self):
        self._events = deque()
        self._lock = threading.Lock()
        self._tpm = max(1, int(os.getenv("EMBEDDING_TPM", "900000")))

    def acquire(self, tokens: int) -> None:
        tokens = max(1, tokens)
        while True:
            with self._lock:
                now = time.time()
                while self._events and now - self._events[0][0] >= 60:
                    self._events.popleft()
                used = sum(item[1] for item in self._events)
                if used + tokens <= self._tpm:
                    self._events.append((now, tokens))
                    return
                wait = 60 - (now - self._events[0][0]) if self._events else 1
            time.sleep(max(0.5, wait))


_RATE_LIMITER = _TokenRateLimiter()


def _approx_tokens(text: str) -> int:
    """Cheap token estimate: ASCII ~4 chars/token; CJK ~1 char/token."""
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    return max(1, ascii_chars // 4 + (len(text) - ascii_chars))


def get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        api_key = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY")
        api_base = os.getenv("EMBEDDING_API_BASE") or os.getenv("OPENAI_API_BASE")
        timeout = float(os.getenv("EMBEDDING_TIMEOUT_SECONDS", "20"))
        _openai_client = OpenAI(api_key=api_key, base_url=api_base, timeout=timeout)
    return _openai_client

def get_local_model(model_name: str):
    global _local_model
    if _local_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            print(f"Loading local embedding model '{model_name}'...")
            _local_model = SentenceTransformer(model_name)
        except ImportError:
            if os.getenv("SOFTWIKI_ALLOW_MOCK_EMBEDDINGS", "").lower() in ("1", "true", "yes"):
                print("WARNING: sentence-transformers missing; using mock random embeddings.")
                _local_model = "fallback"
            else:
                raise RuntimeError(
                    "sentence-transformers is not installed and EMBEDDING_PROVIDER=local. "
                    "Install it, switch to EMBEDDING_PROVIDER=openai, or set "
                    "SOFTWIKI_ALLOW_MOCK_EMBEDDINGS=1 for throwaway testing."
                )
    return _local_model

class WikiEmbedder:
    def __init__(self):
        # Default fallback values
        self.provider = os.getenv("EMBEDDING_PROVIDER", "openai").lower()
        self.model_name = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        
        # Load from model_profiles.yaml if exists
        from softwiki.config import get_config_path
        import yaml
        profiles_path = get_config_path("model_profiles.yaml")
        if os.path.exists(profiles_path):
            try:
                with open(profiles_path, "r", encoding="utf-8") as f:
                    profiles = yaml.safe_load(f).get("profiles", {}) or {}
                    # Try local_embedding first, then embedding
                    profile = profiles.get("local_embedding") or profiles.get("embedding")
                    if profile:
                        self.provider = profile.get("provider", self.provider).lower()
                        self.model_name = profile.get("model", self.model_name)
            except Exception as e:
                print(f"Error loading embedding profile: {e}")

    def _embed_openai(self, texts: List[str]) -> List[List[float]]:
        client = get_openai_client()
        model_lower = self.model_name.lower()
        default_batch = 10 if ("text-embedding-v4" in model_lower or "embedding-v4" in model_lower) else 100
        batch_size = max(1, int(os.getenv("EMBEDDING_BATCH_SIZE", str(default_batch))))
        concurrency = max(1, int(os.getenv("EMBEDDING_CONCURRENCY", "4")))
        batches = [texts[i:i + batch_size] for i in range(0, len(texts), batch_size)]

        max_retries = max(0, int(os.getenv("EMBEDDING_MAX_RETRIES", "1")))
        dimensions = os.getenv("EMBEDDING_DIMENSIONS")
        extra = {"dimensions": int(dimensions)} if dimensions else {}

        def embed_batch(batch):
            _RATE_LIMITER.acquire(sum(_approx_tokens(text) for text in batch))
            for attempt in range(max_retries + 1):
                try:
                    response = client.embeddings.create(
                        input=batch, model=self.model_name, **extra
                    )
                    return [data.embedding for data in response.data]
                except Exception:
                    if attempt >= max_retries:
                        raise
                    time.sleep(min(5, 0.5 * (attempt + 1)))

        results: List[List[List[float]] | None] = [None] * len(batches)
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {
                pool.submit(embed_batch, batch): index
                for index, batch in enumerate(batches)
            }
            for future in as_completed(futures):
                results[futures[future]] = future.result()

        return [vector for batch in results if batch for vector in batch]

    def _embed_local(self, texts: List[str]) -> List[List[float]]:
        model = get_local_model(self.model_name)
        if model == "fallback":
            embeddings = []
            for text in texts:
                np.random.seed(hash(text) % (2**32 - 1))
                vec = np.random.randn(384)
                norm = np.linalg.norm(vec)
                vec = vec / norm if norm > 0 else vec
                embeddings.append(vec.tolist())
            return embeddings
        return model.encode(texts).tolist()

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        if self.provider == "openai":
            return self._embed_openai(texts)
        if self.provider in ("local", "sentence-transformers"):
            return self._embed_local(texts)
        raise ValueError(f"Unsupported EMBEDDING_PROVIDER: {self.provider}")

    def embed_query(self, text: str) -> List[float]:
        return self.embed_texts([text])[0]
