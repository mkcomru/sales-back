"""Tests for simulator models."""

import pytest
from tortoise.exceptions import IntegrityError

from src.backend.modules.simulator.models import SimulatorSession

pytestmark = pytest.mark.asyncio


async def test_simulator_session_creation(authenticated_user_with_company):
    """Test creating a simulator session."""
    company_user = authenticated_user_with_company["company_user"]

    session = await SimulatorSession.create(
        company_user=company_user,
        messages=[],
        context={},
    )

    assert session.id is not None
    assert session.company_user_id == company_user.id
    assert session.messages == []
    assert session.context == {}
    assert session.created_at is not None
    assert session.updated_at is not None


async def test_simulator_session_stores_messages(authenticated_user_with_company):
    """Test storing messages in session."""
    company_user = authenticated_user_with_company["company_user"]

    messages = [
        {"role": "user", "content": "Hello", "timestamp": "2025-01-01T00:00:00Z"},
        {
            "role": "assistant",
            "content": "Hi there!",
            "timestamp": "2025-01-01T00:00:01Z",
        },
    ]

    session = await SimulatorSession.create(
        company_user=company_user,
        messages=messages,
        context={"test_key": "test_value"},
    )

    assert len(session.messages) == 2
    assert session.messages[0]["role"] == "user"
    assert session.messages[1]["role"] == "assistant"
    assert session.context["test_key"] == "test_value"


async def test_simulator_session_unique_per_company_user(
    authenticated_user_with_company,
):
    """Test that only one session exists per company_user."""
    company_user = authenticated_user_with_company["company_user"]

    session1 = await SimulatorSession.create(
        company_user=company_user,
        messages=[],
        context={},
    )

    with pytest.raises(IntegrityError):
        await SimulatorSession.create(
            company_user=company_user,
            messages=[],
            context={},
        )

    sessions = await SimulatorSession.filter(company_user=company_user).all()
    assert len(sessions) == 1
    assert sessions[0].id == session1.id


async def test_simulator_session_cascade_delete_on_company_user_delete(
    authenticated_user_with_company,
):
    """Test that session is deleted when company_user is deleted."""
    company_user = authenticated_user_with_company["company_user"]

    session = await SimulatorSession.create(
        company_user=company_user,
        messages=[{"role": "user", "content": "test"}],
        context={},
    )

    session_id = session.id

    await company_user.delete()

    deleted_session = await SimulatorSession.filter(id=session_id).first()
    assert deleted_session is None


async def test_simulator_session_updates_timestamp(authenticated_user_with_company):
    """Test that updated_at changes on save."""
    company_user = authenticated_user_with_company["company_user"]

    session = await SimulatorSession.create(
        company_user=company_user,
        messages=[],
        context={},
    )

    original_updated_at = session.updated_at

    session.messages = [{"role": "user", "content": "new message"}]
    await session.save()

    assert session.updated_at >= original_updated_at
