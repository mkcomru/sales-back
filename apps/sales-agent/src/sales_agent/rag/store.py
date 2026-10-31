from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qm

from common import SalesAgentSettings


@dataclass
class Chunk:
    id: str
    kb: str
    source_id: str | None
    doc_url: str | None
    title: str | None
    content: str
    h_path: list[str] | None
    keywords: list[str] | None
    lang: str | None
    meta: dict[str, Any]


class QdrantStore:
    def __init__(self, settings: SalesAgentSettings | None = None) -> None:
        self._settings = settings or SalesAgentSettings()
        q = self._settings.rag.qdrant
        if not q.url or not q.api_key:
            raise ValueError("Qdrant Cloud is not configured")
        self._client = AsyncQdrantClient(url=q.url, api_key=q.api_key.get_secret_value())
        self._collection_prefix = q.collection_prefix or "kb"

    def _collection(self, kb: str) -> str:
        return f"{self._collection_prefix}__{kb}"

    async def ensure_collection(self, kb: str, vector_size: int = 1024) -> None:
        name = self._collection(kb)
        exists = await self._client.collection_exists(name)
        if exists:
            return
        await self._client.create_collection(
            collection_name=name,
            vectors_config=qm.VectorParams(size=vector_size, distance=qm.Distance.COSINE),
            # AICODE-NOTE: Enable sparse if needed later; we start with dense-only
        )

    async def upsert(
        self,
        kb: str,
        ids: Sequence[str],
        vectors: Sequence[list[float]],
        payloads: Sequence[dict[str, Any]],
    ) -> None:
        name = self._collection(kb)
        points = [qm.PointStruct(id=ids[i], vector=vectors[i], payload=payloads[i]) for i in range(len(ids))]
        await self._client.upsert(collection_name=name, points=points)

    async def search(
        self,
        kb: str,
        query_vector: list[float],
        filter_: qm.Filter | None = None,
        limit: int = 20,
    ) -> list[qm.ScoredPoint]:
        name = self._collection(kb)
        return await self._client.search(
            collection_name=name,
            query_vector=query_vector,
            limit=limit,
            query_filter=filter_,
        )
