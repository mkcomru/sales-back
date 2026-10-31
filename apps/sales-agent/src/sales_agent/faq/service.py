from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from common import SalesAgentSettings

from .loader import FaqLoader
from .matcher import FaqMatcher
from .models import FaqData, FaqMatch
from src.sales_agent.core.telemetry import get_tracer
from src.sales_agent.rag.embeddings import EmbeddingsClient
from src.sales_agent.rag.store import QdrantStore


class FaqService:
    def __init__(self, *, settings: SalesAgentSettings | None = None) -> None:
        self.log = structlog.get_logger()
        self._settings = settings or SalesAgentSettings()
        # Resolve path: prefer settings.faq.path else default to config/faq.json in app
        base = Path(__file__).resolve().parents[1]
        default_path = base / "config" / "faq.json"
        path_str = self._settings.faq.path or str(default_path)
        self._loader = FaqLoader(Path(path_str))
        self._matcher = FaqMatcher(self._settings)
        self._data: FaqData | None = None
        # Optional vector-store backed index
        self._use_qdrant: bool = bool(getattr(self._settings.faq, "use_qdrant", False))
        self._kb_name: str = getattr(self._settings.faq, "kb_name", "faq")
        self._store: QdrantStore | None = None
        self._emb: EmbeddingsClient | None = None
        self._last_indexed_mtime_ns: int | None = None

    async def ensure_ready(self) -> None:
        # Load and pre-embed index (if embeddings enabled)
        tracer = get_tracer(self._settings)
        with tracer.start_span("faq.ensure_ready", metadata={"path": str(self._loader._path)}):
            self._data = self._loader.load()
            try:
                await self._matcher.prepare_index(self._data)
            except Exception:
                # AICODE-NOTE: embeddings optional; fallback to keyword matching
                pass

            # Optional: index FAQ into Qdrant for vector search
            if self._use_qdrant:
                if self._store is None:
                    try:
                        self._store = QdrantStore(self._settings)
                    except Exception:
                        self._store = None
                if self._emb is None:
                    try:
                        self._emb = EmbeddingsClient(self._settings)
                    except Exception:
                        self._emb = None

                if self._store is not None and self._emb is not None:
                    await self._store.ensure_collection(
                        self._kb_name,
                        vector_size=self._settings.rag.embedding.dimension,
                    )

                    mtime_ns = self._loader._path.stat().st_mtime_ns
                    if self._last_indexed_mtime_ns != mtime_ns:
                        texts: list[str] = []
                        ids: list[str] = []
                        payloads: list[dict[str, Any]] = []
                        for cat in self._data.categories if self._data else []:
                            for i, q in enumerate(cat.questions):
                                rid = f"{cat.category}::{i}"
                                ids.append(rid)
                                enrich = "\n".join(q.keywords) if q.keywords else ""
                                text = (q.question + "\n" + enrich).strip()
                                texts.append(text)
                                payloads.append(
                                    {
                                        "id": rid,
                                        "kb": self._kb_name,
                                        "doc_url": None,
                                        "chunk_title": cat.category,
                                        "h_path": [cat.category, f"q{i}"],
                                        "keywords": q.keywords,
                                        "question": q.question,
                                        "answer": q.answer,
                                        "content": q.answer,
                                    }
                                )

                        if texts:
                            vecs = await self._emb.aembed_documents(texts)
                            await self._store.upsert(self._kb_name, ids=ids, vectors=vecs, payloads=payloads)
                            self._last_indexed_mtime_ns = mtime_ns

    async def find_best(self, question: str) -> FaqMatch | None:
        if not self._settings.faq.enabled:
            return None
        if self._data is None:
            await self.ensure_ready()
        data = self._data or FaqData(categories=[])
        tracer = get_tracer(self._settings)
        with tracer.start_span("faq.find_best", input={"question": question[:200]}):
            # If Qdrant-backed index is enabled, search there first
            if self._use_qdrant and self._store is not None:
                try:
                    if self._emb is None:
                        self._emb = EmbeddingsClient(self._settings)
                    qv = await self._emb.aembed_query(question)
                    points = await self._store.search(self._kb_name, query_vector=qv, limit=10)
                    if points:
                        p = points[0]
                        pl = p.payload or {}
                        match = FaqMatch(
                            category=str(pl.get("chunk_title") or pl.get("category") or ""),
                            question=str(pl.get("question") or ""),
                            answer=str(pl.get("answer") or ""),
                            keywords=list(pl.get("keywords") or []),
                            score=float(p.score or 0.0),
                        )
                    else:
                        match = None
                except Exception:
                    match = await self._matcher.find_best(data, question)
            else:
                match = await self._matcher.find_best(data, question)
            if match is not None:
                tracer.update_current_span(
                    output={
                        "category": match.category,
                        "question": match.question,
                        "score": round(match.score, 4),
                    }
                )
            return match


_faq_service: FaqService | None = None


def get_faq_service() -> FaqService:
    global _faq_service
    if _faq_service is None:
        _faq_service = FaqService()
    return _faq_service
