from __future__ import annotations

import math

import structlog

from common import SalesAgentSettings

from .models import FaqData, FaqMatch
from src.sales_agent.rag.embeddings import EmbeddingsClient
from src.sales_agent.rag.reranker import Reranker


def _cosine_sim(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    if len(a) != len(b):
        # best effort: truncate to min length
        n = min(len(a), len(b))
        a = a[:n]
        b = b[:n]
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class FaqMatcher:
    def __init__(self, settings: SalesAgentSettings | None = None) -> None:
        self.log = structlog.get_logger()
        self._settings = settings or SalesAgentSettings()
        # Embeddings are optional; fallback to naive keyword match if not configured
        try:
            self._emb = EmbeddingsClient(self._settings)
            self._embedding_enabled = True
        except Exception:
            self._emb = None
            self._embedding_enabled = False
        self._cache: dict[str, list[float]] = {}
        # Optional reranker
        self._use_reranker = bool(self._settings.rag.reranker.enabled)
        self._reranker: Reranker | None = None
        if self._use_reranker:
            try:
                self._reranker = Reranker(self._settings)
            except Exception:
                self._use_reranker = False

    async def _embed(self, text: str) -> list[float]:
        if self._emb is None:
            return []
        return await self._emb.aembed_query(text)

    async def prepare_index(self, data: FaqData) -> None:
        if not self._embedding_enabled:
            return
        # Precompute embeddings per unique question+keywords
        tasks: list[tuple[str, str]] = []
        for cat in data.categories:
            for q in cat.questions:
                key = q.question
                if key in self._cache:
                    continue
                enrich = "\n".join(q.keywords) if q.keywords else ""
                text = (q.question + "\n" + enrich).strip()
                tasks.append((key, text))

        # Batch embed in small groups to avoid large requests
        BATCH = 16
        for i in range(0, len(tasks), BATCH):
            batch = tasks[i : i + BATCH]  # noqa: E203
            if not batch:
                continue
            texts = [t[1] for t in batch]
            vecs = await self._emb.aembed_documents(texts) if self._emb else []
            for (key, _), vec in zip(batch, vecs, strict=False):
                self._cache[key] = vec

    async def find_best(self, data: FaqData, query: str) -> FaqMatch | None:
        if not query or not data.categories:
            return None

        # Build candidate list with combined score = 0.7 * sim + 0.3 * keyword_overlap
        candidates: list[tuple[FaqMatch, float, float]] = []  # (match, sim, kw_score)

        lowered = query.lower()
        qv: list[float] = []
        if self._embedding_enabled and self._emb is not None:
            qv = await self._embed(query)

        for cat in data.categories:
            for q in cat.questions:
                # Keyword overlap
                hits = 0
                for kw in q.keywords:
                    k = kw.lower().strip()
                    if not k:
                        continue
                    if k in lowered:
                        hits += 1
                    # Simple stem-like boost: prefix match (e.g., "вторич")
                    if len(k) >= 6 and any(tok.startswith(k[:6]) for tok in lowered.split()):
                        hits += 1
                if q.question and q.question.lower() in lowered:
                    hits += 1
                kw_score = float(hits) / float(max(1, len(q.keywords) + 1))

                # Embedding similarity
                sim = 0.0
                if qv:
                    dv = self._cache.get(q.question)
                    if not dv:
                        enrich = "\n".join(q.keywords) if q.keywords else ""
                        text = (q.question + "\n" + enrich).strip()
                        dv = await self._embed(text)
                        self._cache[q.question] = dv
                    sim = _cosine_sim(qv, dv)

                combined = 0.7 * sim + 0.3 * kw_score
                candidates.append(
                    (
                        FaqMatch(
                            category=cat.category,
                            question=q.question,
                            answer=q.answer,
                            keywords=list(q.keywords),
                            score=combined,
                        ),
                        sim,
                        kw_score,
                    )
                )

        if not candidates:
            return None

        # Preselect by combined score
        candidates.sort(key=lambda x: x[0].score, reverse=True)
        preselected = candidates[: max(10, min(20, len(candidates)))]

        # Optional rerank with cross-encoder for better semantic ordering
        if self._use_reranker and self._reranker is not None:
            docs = [f"{m.question}\n{m.answer}" for (m, _s, _k) in preselected]
            try:
                topn = min(5, len(docs))
                order = self._reranker.rerank(query, docs, top_n=topn)
                # Move top reranked items to the front preserving others
                reordered = [preselected[i] for i in order]
                tail = [p for j, p in enumerate(preselected) if j not in order]
                preselected = reordered + tail
            except Exception:
                pass

        best = preselected[0][0]
        return best
