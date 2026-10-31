from __future__ import annotations

from collections.abc import Sequence

from cohere import ClientV2 as CohereClient

from common import SalesAgentSettings


class Reranker:
    """Wrapper over Cohere Rerank API (cloud).

    Activated if settings.rag.reranker.enabled=true and token/model are provided.
    """

    def __init__(self, settings: SalesAgentSettings | None = None) -> None:
        self._settings = settings or SalesAgentSettings()
        cfg = self._settings.rag.reranker
        if not cfg.enabled:
            raise RuntimeError("Reranker is disabled by config")
        if not cfg.api_key:
            raise ValueError("Reranker API key is not configured")

        # Cohere SDK v5: prefer ClientV2; API key via constructor
        self._client = CohereClient(api_key=cfg.api_key.get_secret_value())
        self._model = cfg.model or "rerank-english-v3.0"

    def rerank(self, query: str, documents: Sequence[str], top_n: int) -> list[int]:
        # ClientV2 exposes v2 endpoints directly as methods
        resp = self._client.rerank(
            model=self._model,
            query=query,
            documents=list(documents),
            top_n=top_n,
        )
        # Return document indices in relevance order
        return [item.index for item in resp.results]
