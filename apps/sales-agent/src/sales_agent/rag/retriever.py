from __future__ import annotations

from typing import Any

from common import SalesAgentSettings

from .embeddings import EmbeddingsClient
from .reranker import Reranker
from .store import QdrantStore


class Retriever:
    def __init__(self, settings: SalesAgentSettings | None = None) -> None:
        self._settings = settings or SalesAgentSettings()
        self._emb = EmbeddingsClient(self._settings)
        self._store = QdrantStore(self._settings)
        self._use_reranker = bool(self._settings.rag.reranker.enabled)
        self._reranker: Reranker | None = None
        if self._use_reranker:
            try:
                self._reranker = Reranker(self._settings)
            except Exception:
                # AICODE-NOTE: Fail-open: if reranker is not configured,
                # continue without it
                self._use_reranker = False

    def _resolve_kb_name(self, kb: str | None = None) -> str:
        if kb:
            return kb
        try:
            from src.sales_agent.services.company_context import get_company_spec

            spec = get_company_spec()
            return spec["collection_name"]
        except (RuntimeError, KeyError):
            return self._settings.rag.default_kb

    async def ensure_ready(self, kb: str | None = None) -> None:
        kb_name = self._resolve_kb_name(kb)
        await self._store.ensure_collection(
            kb_name,
            vector_size=self._settings.rag.embedding.dimension,
        )

    async def retrieve(self, query: str, kb: str | None = None, top_k: int = 5) -> list[dict[str, Any]]:
        kb_name = self._resolve_kb_name(kb)
        qv = await self._emb.aembed_query(query)
        points = await self._store.search(
            kb_name,
            qv,
            limit=max(10, top_k * 3),
        )
        # Simple top-k by qdrant scores for v1; reranker can refine later
        selected = points[:top_k]

        # If reranker is enabled, rerank candidate payloads
        if self._use_reranker and self._reranker is not None:
            texts = [(p.payload or {}).get("content", "") for p in points]
            order = self._reranker.rerank(query, texts, top_n=top_k)
            selected = [points[i] for i in order]

        result: list[dict[str, Any]] = []
        for p in selected:
            payload = p.payload or {}
            result.append(
                {
                    "source": "rag",
                    "record_id": payload.get("id") or str(p.id),
                    "title": payload.get("chunk_title"),
                    "path": payload.get("h_path"),
                    "topic": payload.get("topic"),
                    "summary": payload.get("summary"),
                    "content": payload.get("content"),
                    "score": p.score,
                    "url": payload.get("doc_url"),
                    "keywords": payload.get("keywords"),
                }
            )
        return result
