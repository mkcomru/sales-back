from __future__ import annotations

import asyncio
from collections.abc import Sequence

from openai import AsyncOpenAI

from common import SalesAgentSettings


class EmbeddingsClient:
    """OpenAI Python SDK client (OpenAI-compatible) for embeddings.

    Configured via `settings.rag.embedding` (base_url, api_key, model)
    and automatically adds BGE prefixes for documents and queries.
    """

    def __init__(self, settings: SalesAgentSettings | None = None) -> None:
        self._settings = settings or SalesAgentSettings()
        cfg = self._settings.rag.embedding
        if not cfg.base_url or not cfg.api_key:
            raise ValueError("RAG embedding API is not configured")

        self._client = AsyncOpenAI(
            base_url=cfg.base_url.rstrip("/"),
            api_key=cfg.api_key.get_secret_value(),
        )
        self._model = cfg.model
        self._dimension = cfg.dimension

    async def aembed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        resp = await self._client.embeddings.create(
            model=self._model,
            input=list(texts),
            encoding_format="float",
            # Some providers accept `dimensions`; we omit for compatibility
        )
        vectors = [item.embedding for item in resp.data]
        return vectors

    async def aembed_query(self, query: str) -> list[float]:
        vecs = await self._client.embeddings.create(
            model=self._model,
            input=[query],
            encoding_format="float",
        )
        return vecs.data[0].embedding if vecs.data else []

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return asyncio.get_event_loop().run_until_complete(self.aembed_documents(texts))

    def embed_query(self, query: str) -> list[float]:
        return asyncio.get_event_loop().run_until_complete(self.aembed_query(query))
