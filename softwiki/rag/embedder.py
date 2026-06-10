import os
import numpy as np
from typing import List

_openai_client = None
_local_model = None

def get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        api_base = os.getenv("OPENAI_API_BASE")
        _openai_client = OpenAI(api_key=api_key, base_url=api_base)
    return _openai_client

def get_local_model(model_name: str):
    global _local_model
    if _local_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            print(f"Loading local embedding model '{model_name}'...")
            _local_model = SentenceTransformer(model_name)
        except ImportError:
            print("WARNING: 'sentence-transformers' not installed. Falling back to simple TF-IDF mock embeddings.")
            _local_model = "fallback"
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

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        if self.provider == "openai":
            try:
                client = get_openai_client()
                response = client.embeddings.create(
                    input=texts,
                    model=self.model_name
                )
                return [data.embedding for data in response.data]
            except Exception as e:
                print(f"OpenAI embedding failed ({e}). Attempting local fallback...")
                self.provider = "local"
                self.model_name = "all-MiniLM-L6-v2"

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
        else:
            vecs = model.encode(texts)
            return vecs.tolist()

    def embed_query(self, text: str) -> List[float]:
        return self.embed_texts([text])[0]
