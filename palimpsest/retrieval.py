"""
PALIMPSEST Retrieval Engine
Semantic retrieval of memory items using sentence-transformers and FAISS.
"""

from __future__ import annotations

import numpy as np

from config import Config
from palimpsest.models import MemoryItem


class RetrievalEngine:
    """Semantic search over memory items using FAISS."""

    def __init__(self, config: Config):
        self.config = config
        self._model = None
        self._index = None
        self._items: list[MemoryItem] = []
        self._dim: int = 384  # default for all-MiniLM-L6-v2

    def _load_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.config.embedding_model)
            except Exception:
                self._model = "mock"

    def _load_index(self):
        if self._index is None:
            try:
                import faiss
                self._index = faiss.IndexFlatL2(self._dim)
            except Exception:
                self._index = "mock"

    def embed(self, text: str) -> list[float]:
        """Embed a single text string."""
        self._load_model()
        if self._model == "mock":
            # Deterministic mock embedding based on hash
            import hashlib
            h = int(hashlib.md5(text.encode()).hexdigest(), 16)
            rng = np.random.default_rng(h % (2**32))
            return rng.random(self._dim).tolist()
        vec = self._model.encode([text])[0]
        return vec.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts."""
        return [self.embed(t) for t in texts]

    def build_index(self, items: list[MemoryItem]):
        """Build a FAISS index from a list of memory items."""
        self._load_index()
        self._items = []
        if self._index == "mock":
            self._items = items
            return

        import faiss
        self._index = faiss.IndexFlatL2(self._dim)

        for item in items:
            if item.embedding:
                vec = np.array([item.embedding], dtype=np.float32)
                self._index.add(vec)
                self._items.append(item)

    def retrieve(self, query: str, top_k: int = 10) -> list[MemoryItem]:
        """Return the top_k most relevant items for a query."""
        if not self._items:
            return []

        query_vec = self.embed(query)

        if self._index == "mock":
            # Mock: return items sorted by naive string overlap
            scored = []
            q_words = set(query.lower().split())
            for item in self._items:
                i_words = set(item.content.lower().split())
                score = len(q_words & i_words)
                scored.append((score, item))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [item for _, item in scored[:top_k]]

        try:
            import faiss
            q = np.array([query_vec], dtype=np.float32)
            k = min(top_k, len(self._items))
            _, indices = self._index.search(q, k)
            return [self._items[i] for i in indices[0] if 0 <= i < len(self._items)]
        except Exception:
            return self._items[:top_k]

    def update_index(self, item: MemoryItem):
        """Add a single item to the index."""
        self._load_index()
        if not item.embedding:
            return
        self._items.append(item)

        if self._index == "mock":
            return
        try:
            vec = np.array([item.embedding], dtype=np.float32)
            self._index.add(vec)
        except Exception:
            pass
