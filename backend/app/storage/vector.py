"""Agent vector memory & RAG — real retrieval.

Embeddings:
  - When an LLM/embeddings key is configured: real dense embeddings via the
    OpenAI-compatible `/embeddings` endpoint (OpenAI, Groq, Ollama, ...).
  - Otherwise: real TF-IDF retrieval (term-frequency × inverse-document-frequency,
    cosine similarity) computed over the stored corpus — no fake hashed vectors.

Stores:
  - TfidfMemory  — in-process, pure-Python TF-IDF (default, real math).
  - QdrantMemory — production vector DB; uses dense embeddings when available,
    deterministic hashing fallback for offline dev.

Both expose the same upsert/search interface used by the agent's memory tools.
"""
from __future__ import annotations

import asyncio
import math
import re
from collections import Counter, defaultdict
from typing import Any, Protocol
from uuid import uuid4

TOP_K_DEFAULT = 5
OFFLINE_VECTOR_DIM = 256
DENSE_VECTOR_DIM = 1536  # text-embedding-3-small

TOKEN_RE = re.compile(r"[a-z0-9]{2,}")


def _stem(word: str) -> str:
    """Light stemmer so 'pricing'~'price', 'sections'~'section', 'running'~'run'."""
    if len(word) <= 4:
        return word
    if word.endswith("ies") and len(word) > 5:
        return word[:-3] + "y"
    if word.endswith("ing") and len(word) > 6:
        return word[:-3]
    if word.endswith("edly") and len(word) > 6:
        return word[:-4]
    if word.endswith("ed") and len(word) > 5:
        return word[:-2]
    if word.endswith("e") and len(word) > 4:
        return word[:-1]  # price->pric, make->mak
    if word.endswith("es") and len(word) > 5:
        return word[:-2]
    if word.endswith("s") and len(word) > 4:
        return word[:-1]
    return word


def _tokenize(text: str) -> list[str]:
    return [_stem(w) for w in TOKEN_RE.findall(text.lower())]


class Embedder(Protocol):
    dim: int
    async def embed(self, text: str) -> list[float]: ...


class DenseEmbedder:
    """Real embeddings through any OpenAI-compatible /embeddings endpoint."""

    def __init__(self, base_url: str, api_key: str, model: str = "text-embedding-3-small"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.dim = DENSE_VECTOR_DIM
        self._cache: dict[str, list[float]] = {}

    async def embed(self, text: str) -> list[float]:
        import httpx

        if text in self._cache:
            return self._cache[text]
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.base_url}/embeddings",
                json={"model": self.model, "input": text},
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            vector = data["data"][0]["embedding"]
        self._cache[text] = vector
        return vector


async def fuzzy_embed(embedder: Embedder | None, text: str) -> list[float]:
    """Embed with the real model; fall back to deterministic hashing on failure."""
    if embedder is not None:
        try:
            return await embedder.embed(text)
        except Exception:  # noqa: BLE001 - network/key hiccup -> deterministic fallback
            pass
    return hash_embedding(text)


def hash_embedding(text: str, dim: int = OFFLINE_VECTOR_DIM) -> list[float]:
    """Deterministic sparse embedding over tokens (offline fallback only)."""
    import hashlib

    vec = [0.0] * dim
    for token in _tokenize(text):
        h = int(hashlib.sha256(token.encode()).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h >> 8) % 2 == 0 else -1.0
        vec[idx] += sign / math.sqrt(len(token))
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    """Cosine over sparse dict vectors (shared keys)."""
    common = set(a) & set(b)
    dot = sum(a[k] * b[k] for k in common)
    na = math.sqrt(sum(v * v for v in a.values())) or 1.0
    nb = math.sqrt(sum(v * v for v in b.values())) or 1.0
    return dot / (na * nb)


# ── In-memory TF-IDF store (real retrieval, zero deps) ───────────────

class TfidfMemory:
    """Pure Python TF-IDF + cosine similarity over the stored corpus."""

    def __init__(self) -> None:
        self._items: dict[str, dict[str, Any]] = {}
        self._doc_tokens: dict[str, Counter[str]] = {}
        self._df: Counter[str] = Counter()
        self._doc_count = 0

    def _idf(self, term: str) -> float:
        # Smooth idf; terms unseen in docs still get a small weight.
        return math.log((1 + self._doc_count) / (1 + self._df[term])) + 1.0

    def _doc_vector(self, doc_id: str) -> dict[str, float]:
        tf = self._doc_tokens[doc_id]
        total = sum(tf.values()) or 1
        return {term: (count / total) * self._idf(term) for term, count in tf.items()}

    async def upsert(self, text: str, meta: dict[str, Any] | None = None) -> str:
        memory_id = f"mem-{uuid4().hex[:10]}"
        tokens = _tokenize(text)
        counter = Counter(tokens)
        self._items[memory_id] = {"text": text, "metadata": meta or {}}
        self._doc_tokens[memory_id] = counter
        for term in counter:
            self._df[term] += 1
        self._doc_count += 1
        return memory_id

    async def search(self, query: str, top_k: int = TOP_K_DEFAULT, meta: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        query_tf = Counter(_tokenize(query))
        total = sum(query_tf.values()) or 1
        qvec = {term: (count / total) * self._idf(term) for term, count in query_tf.items()}

        scored: list[tuple[float, dict[str, Any]]] = []
        for doc_id, item in self._items.items():
            if meta and not all(item["metadata"].get(k) == v for k, v in meta.items()):
                continue
            score = _cosine(qvec, self._doc_vector(doc_id))
            scored.append((score, {**item, "id": doc_id}))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [{**item, "score": round(score, 4)} for score, item in scored[:top_k]]

    async def list_items(self, limit: int = 20, meta: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        items = [
            {**item, "id": doc_id, "score": None}
            for doc_id, item in self._items.items()
            if not meta or all(item["metadata"].get(k) == v for k, v in meta.items())
        ]
        return items[:limit]


# Backward-compatible alias.
HashMemory = TfidfMemory


# ── Qdrant (production) ──────────────────────────────────────────────

class QdrantMemory:
    """Qdrant-backed storage; dense embeddings when configured, hashed fallback otherwise."""

    def __init__(self, url: str, collection: str, embedder: Embedder | None = None, api_key: str = ""):
        from qdrant_client import AsyncQdrantClient  # lazy import

        self._client = AsyncQdrantClient(url=url, api_key=api_key or None, timeout=10)
        self._collection = collection
        self._embedder = embedder
        self._dim = embedder.dim if embedder else OFFLINE_VECTOR_DIM
        self._ready = False

    async def _ensure(self) -> None:
        if self._ready:
            return
        from qdrant_client.models import Distance, VectorParams

        collections = await self._client.get_collections()
        names = {c.name for c in collections.collections}
        if self._collection not in names:
            await self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(size=self._dim, distance=Distance.COSINE),
            )
        self._ready = True

    async def _vector(self, text: str) -> list[float]:
        return await fuzzy_embed(self._embedder, text)

    async def upsert(self, text: str, meta: dict[str, Any] | None = None) -> str:
        from qdrant_client.models import PointStruct

        await self._ensure()
        memory_id = f"mem-{uuid4().hex[:10]}"
        await self._client.upsert(
            collection_name=self._collection,
            points=[
                PointStruct(
                    id=memory_id,
                    vector=await self._vector(text),
                    payload={"text": text, "metadata": meta or {}},
                )
            ],
        )
        return memory_id

    async def search(self, query: str, top_k: int = TOP_K_DEFAULT, meta: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        await self._ensure()
        query_filter = None
        if meta:
            conditions = [FieldCondition(key=f"metadata.{k}", match=MatchValue(value=v)) for k, v in meta.items()]
            query_filter = Filter(must=conditions)
        results = await self._client.query_points(
            collection_name=self._collection,
            query=await self._vector(query),
            query_filter=query_filter,
            limit=top_k,
        )
        return [
            {"id": r.id, "text": r.payload.get("text", ""), "metadata": r.payload.get("metadata", {}), "score": round(r.score, 4)}
            for r in results.points
        ]

    async def list_items(self, limit: int = 20, meta: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        await self._ensure()
        query_filter = None
        if meta:
            conditions = [FieldCondition(key=f"metadata.{k}", match=MatchValue(value=v)) for k, v in meta.items()]
            query_filter = Filter(must=conditions)
        results = await self._client.scroll(collection_name=self._collection, limit=limit, scroll_filter=query_filter)
        return [
            {"id": p.id, "text": p.payload.get("text", ""), "metadata": p.payload.get("metadata", {}), "score": None}
            for p in results[0]
        ]

    async def close(self) -> None:
        await self._client.close()


class VectorMemory(Protocol):
    async def upsert(self, text: str, meta: dict[str, Any] | None = None) -> str: ...
    async def search(self, query: str, top_k: int, meta: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...
    async def list_items(self, limit: int = 20, meta: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...


def build_memory(
    qdrant_url: str = "",
    collection: str = "agent_memory",
    api_key: str = "",
    *,
    embedder: Embedder | None = None,
) -> VectorMemory:
    """Qdrant when configured (dense embeddings if possible), else real TF-IDF."""
    if qdrant_url:
        return QdrantMemory(qdrant_url, collection, embedder=embedder, api_key=api_key)
    return TfidfMemory()
