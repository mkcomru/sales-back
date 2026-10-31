"""Tests for FAQ service module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from common import SalesAgentSettings

from src.sales_agent.faq.models import FaqData, FaqMatch
from src.sales_agent.faq.service import FaqService, get_faq_service


class TestFaqServiceInit:
    """Test FaqService initialization."""

    def test_init_success(self, settings: SalesAgentSettings) -> None:
        """Test successful initialization."""
        service = FaqService(settings=settings)
        assert service._settings is settings

    def test_init_default_settings(self) -> None:
        """Test initialization with default settings."""
        service = FaqService()
        assert service._settings is not None

    def test_init_custom_path(self, settings: SalesAgentSettings, tmp_path: Path) -> None:
        """Test initialization with custom FAQ path."""
        faq_file = tmp_path / "custom_faq.json"
        faq_file.write_text('{"categories": []}')
        settings.faq.path = str(faq_file)

        service = FaqService(settings=settings)
        assert service._loader._path == faq_file


class TestEnsureReady:
    """Test ensure_ready method."""

    @pytest.mark.asyncio
    async def test_ensure_ready_loads_data(self, settings: SalesAgentSettings, tmp_path: Path) -> None:
        """Test ensure_ready loads FAQ data."""
        faq_file = tmp_path / "faq.json"
        faq_file.write_text('{"categories": []}')

        with patch.object(settings, "faq") as mock_faq:
            mock_faq.path = str(faq_file)
            service = FaqService(settings=settings)

            with patch.object(service._matcher, "prepare_index", new_callable=AsyncMock):
                await service.ensure_ready()

                assert service._data is not None

    @pytest.mark.asyncio
    async def test_ensure_ready_handles_embeddings_error(self, settings: SalesAgentSettings, tmp_path: Path) -> None:
        """Test ensure_ready handles embeddings errors gracefully."""
        faq_file = tmp_path / "faq.json"
        faq_file.write_text('{"categories": []}')

        with patch.object(settings, "faq") as mock_faq:
            mock_faq.path = str(faq_file)
            service = FaqService(settings=settings)

            service._matcher.prepare_index = AsyncMock(side_effect=Exception("Embeddings error"))

            await service.ensure_ready()

            assert service._data is not None


class TestFindBest:
    """Test find_best method."""

    @pytest.mark.asyncio
    async def test_find_best_disabled_returns_none(self, settings: SalesAgentSettings) -> None:
        """Test find_best returns None when FAQ is disabled."""
        settings.faq.enabled = False
        service = FaqService(settings=settings)

        result = await service.find_best("test question")

        assert result is None

    @pytest.mark.asyncio
    async def test_find_best_no_match_returns_none(self, settings: SalesAgentSettings, tmp_path: Path) -> None:
        """Test find_best returns None when no match found."""
        faq_file = tmp_path / "faq.json"
        faq_file.write_text('{"categories": []}')

        with patch.object(settings, "faq") as mock_faq:
            mock_faq.path = str(faq_file)
            mock_faq.enabled = True
            service = FaqService(settings=settings)

            service._data = FaqData(categories=[])
            service._matcher.find_best = AsyncMock(return_value=None)

            result = await service.find_best("test question")

            assert result is None

    @pytest.mark.asyncio
    async def test_find_best_returns_match(self, settings: SalesAgentSettings, tmp_path: Path) -> None:
        """Test find_best returns match when found."""
        faq_file = tmp_path / "faq.json"
        faq_file.write_text('{"categories": []}')

        with patch.object(settings, "faq") as mock_faq:
            mock_faq.path = str(faq_file)
            mock_faq.enabled = True
            service = FaqService(settings=settings)

            service._data = FaqData(categories=[])
            match = FaqMatch(
                category="test",
                question="Test question?",
                answer="Test answer",
                keywords=[],
                score=0.9,
            )
            service._matcher.find_best = AsyncMock(return_value=match)

            result = await service.find_best("test question")

            assert result is not None
            assert result.category == "test"
            assert result.score == 0.9

    @pytest.mark.asyncio
    async def test_find_best_uses_qdrant_when_enabled(self, settings: SalesAgentSettings, tmp_path: Path) -> None:
        """Test find_best uses Qdrant when enabled."""
        faq_file = tmp_path / "faq.json"
        faq_file.write_text('{"categories": []}')

        with patch.object(settings, "faq") as mock_faq:
            mock_faq.path = str(faq_file)
            mock_faq.enabled = True
            mock_faq.use_qdrant = True
            mock_faq.kb_name = "faq"
            service = FaqService(settings=settings)

            mock_store = MagicMock()
            mock_store.search = AsyncMock(return_value=[])
            service._store = mock_store

            mock_emb = MagicMock()
            mock_emb.aembed_query = AsyncMock(return_value=[0.1] * 384)
            service._emb = mock_emb

            service._data = FaqData(categories=[])
            service._matcher.find_best = AsyncMock(return_value=None)

            await service.find_best("test question")

            mock_emb.aembed_query.assert_called_once()
            mock_store.search.assert_called_once()


class TestGetFaqService:
    """Test get_faq_service function."""

    def test_get_faq_service_returns_singleton(self) -> None:
        """Test get_faq_service returns same instance."""
        service1 = get_faq_service()
        service2 = get_faq_service()
        assert service1 is service2
