"""Tests for simulator repository."""

import pytest

from src.backend.modules.simulator.models import SimulatorSession
from src.backend.modules.simulator.repository import SimulatorRepository

pytestmark = pytest.mark.asyncio


@pytest.fixture
def repository():
    """Simulator repository fixture."""
    return SimulatorRepository()


async def test_get_or_create_session_creates_new(repository: SimulatorRepository, authenticated_user_with_company):
    """Test get_or_create creates new session if not exists."""
    company_user = authenticated_user_with_company["company_user"]

    session, created = await repository.get_or_create_session(company_user.id)

    assert created is True
    assert session is not None
    assert session.company_user_id == company_user.id
    assert session.messages == []
    assert session.context == {}


async def test_get_or_create_session_returns_existing(repository: SimulatorRepository, authenticated_user_with_company):
    """Test get_or_create returns existing session."""
    company_user = authenticated_user_with_company["company_user"]

    existing_session = await SimulatorSession.create(
        company_user=company_user,
        messages=[{"role": "user", "content": "existing"}],
        context={"key": "value"},
    )

    session, created = await repository.get_or_create_session(company_user.id)

    assert created is False
    assert session.id == existing_session.id
    assert len(session.messages) == 1
    assert session.context["key"] == "value"


async def test_reset_session_clears_data(repository: SimulatorRepository, authenticated_user_with_company):
    """Test reset_session clears messages and context."""
    company_user = authenticated_user_with_company["company_user"]

    session = await SimulatorSession.create(
        company_user=company_user,
        messages=[{"role": "user", "content": "test"}],
        context={"key": "value"},
    )

    await repository.reset_session(company_user.id)

    await session.refresh_from_db()
    assert session.messages == []
    assert session.context == {}


async def test_reset_session_does_nothing_if_not_exists(
    repository: SimulatorRepository, authenticated_user_with_company
):
    """Test reset_session doesn't fail if session doesn't exist."""
    company_user = authenticated_user_with_company["company_user"]

    await repository.reset_session(company_user.id)

    session = await SimulatorSession.filter(company_user=company_user).first()
    assert session is None


async def test_add_message_creates_session_if_needed(repository: SimulatorRepository, authenticated_user_with_company):
    """Test add_message creates session if it doesn't exist."""
    company_user = authenticated_user_with_company["company_user"]

    session = await repository.add_message(
        company_user_id=company_user.id,
        role="user",
        content="Hello",
        timestamp="2025-01-01T00:00:00Z",
    )

    assert session is not None
    assert len(session.messages) == 1
    assert session.messages[0]["role"] == "user"
    assert session.messages[0]["content"] == "Hello"


async def test_add_message_appends_to_existing(repository: SimulatorRepository, authenticated_user_with_company):
    """Test add_message appends to existing session."""
    company_user = authenticated_user_with_company["company_user"]

    existing_session = await SimulatorSession.create(
        company_user=company_user,
        messages=[{"role": "user", "content": "First"}],
        context={},
    )

    session = await repository.add_message(
        company_user_id=company_user.id,
        role="assistant",
        content="Second",
        timestamp="2025-01-01T00:00:01Z",
    )

    assert session.id == existing_session.id
    assert len(session.messages) == 2
    assert session.messages[0]["content"] == "First"
    assert session.messages[1]["content"] == "Second"


async def test_add_message_preserves_order(repository: SimulatorRepository, authenticated_user_with_company):
    """Test that messages maintain order."""
    company_user = authenticated_user_with_company["company_user"]

    for i in range(5):
        await repository.add_message(
            company_user_id=company_user.id,
            role="user" if i % 2 == 0 else "assistant",
            content=f"Message {i}",
            timestamp=f"2025-01-01T00:00:{i:02d}Z",
        )

    session = await SimulatorSession.filter(company_user=company_user).first()
    assert len(session.messages) == 5

    for i, msg in enumerate(session.messages):
        assert msg["content"] == f"Message {i}"
