"""Tests for simulator API endpoints."""

import pytest
from fastapi import status
from httpx import AsyncClient

from src.backend.modules.companies.models import Company
from src.backend.modules.simulator.models import SimulatorSession
from src.backend.modules.users.models import CompanyUser, UserRole

pytestmark = pytest.mark.asyncio


async def test_reset_simulator_session_success(api_client: AsyncClient, authenticated_user_with_company: dict):
    """Test successful simulator session reset."""
    company = authenticated_user_with_company["company"]
    company_user = authenticated_user_with_company["company_user"]
    headers = authenticated_user_with_company["headers"]

    session = await SimulatorSession.create(
        company_user=company_user,
        messages=[{"role": "user", "content": "test", "timestamp": "2025-01-01T00:00:00Z"}],
        context={"test": "data"},
    )

    response = await api_client.post(f"/api/v1/companies/{company.id}/simulator/reset", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["success"] is True
    assert "reset" in data["message"].lower()

    await session.refresh_from_db()
    assert session.messages == []
    assert session.context == {}


async def test_reset_simulator_session_creates_if_not_exists(
    api_client: AsyncClient, authenticated_user_with_company: dict
):
    """Test reset creates session if it doesn't exist."""
    company = authenticated_user_with_company["company"]
    headers = authenticated_user_with_company["headers"]

    response = await api_client.post(f"/api/v1/companies/{company.id}/simulator/reset", headers=headers)
    assert response.status_code == status.HTTP_200_OK


async def test_reset_simulator_session_requires_auth(api_client: AsyncClient, company: Company):
    """Test reset requires authentication."""
    response = await api_client.post(f"/api/v1/companies/{company.id}/simulator/reset")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_reset_simulator_session_requires_admin_role(
    api_client: AsyncClient, authenticated_user_with_company: dict, settings
):
    """Test reset requires admin role (viewer should fail)."""
    company = authenticated_user_with_company["company"]
    # create a separate viewer user to avoid unique
    # constraint with authenticated fixture
    from passlib.context import CryptContext

    from src.backend.modules.auth.service import AuthService
    from src.backend.modules.users.models import User

    pwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=4, deprecated="auto")
    hashed_password = pwd_context.hash("viewer_password_123")
    viewer_user = await User.create(
        first_name="Viewer",
        last_name="User",
        email="viewer@example.com",
        hashed_password=hashed_password,
        is_active=True,
    )

    await CompanyUser.create(user=viewer_user, company=company, role=UserRole.VIEWER)

    auth_service = AuthService(settings)
    viewer_token = auth_service.create_access_token(user_id=viewer_user.id, is_superuser=False)

    response = await api_client.post(
        f"/api/v1/companies/{company.id}/simulator/reset",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


async def test_send_simulator_message_mock_response(api_client: AsyncClient, authenticated_user_with_company: dict):
    """Test sending message to simulator
    (mock response when Sales Agent unavailable)."""
    company = authenticated_user_with_company["company"]
    headers = authenticated_user_with_company["headers"]

    payload = {"text": "Привет!"}
    response = await api_client.post(
        f"/api/v1/companies/{company.id}/simulator/message",
        headers=headers,
        json=payload,
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "text" in data
    assert "timestamp" in data
    assert isinstance(data["text"], str)
    assert len(data["text"]) > 0


async def test_send_simulator_message_saves_to_session(api_client: AsyncClient, authenticated_user_with_company: dict):
    """Test that simulator messages are saved to session."""
    company = authenticated_user_with_company["company"]
    company_user = authenticated_user_with_company["company_user"]
    headers = authenticated_user_with_company["headers"]

    payload = {"text": "Тестовое сообщение"}
    response = await api_client.post(
        f"/api/v1/companies/{company.id}/simulator/message",
        headers=headers,
        json=payload,
    )
    assert response.status_code == status.HTTP_200_OK

    session = await SimulatorSession.filter(company_user=company_user).first()
    assert session is not None
    assert len(session.messages) == 2  # user + assistant

    user_msg = session.messages[0]
    assert user_msg["role"] == "user"
    assert user_msg["content"] == "Тестовое сообщение"

    assistant_msg = session.messages[1]
    assert assistant_msg["role"] == "assistant"
    assert len(assistant_msg["content"]) > 0


async def test_send_simulator_message_validates_text(api_client: AsyncClient, authenticated_user_with_company: dict):
    """Test that empty text is rejected."""
    company = authenticated_user_with_company["company"]
    headers = authenticated_user_with_company["headers"]

    payload = {"text": ""}
    response = await api_client.post(
        f"/api/v1/companies/{company.id}/simulator/message",
        headers=headers,
        json=payload,
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


async def test_send_simulator_message_requires_auth(api_client: AsyncClient, company: Company):
    """Test that sending message requires authentication."""
    payload = {"text": "test"}
    response = await api_client.post(f"/api/v1/companies/{company.id}/simulator/message", json=payload)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


async def test_send_simulator_message_company_not_found(api_client: AsyncClient, authenticated_user_with_company: dict):
    """Test that nonexistent company returns 404."""
    headers = authenticated_user_with_company["headers"]
    payload = {"text": "test"}
    response = await api_client.post("/api/v1/companies/99999/simulator/message", headers=headers, json=payload)
    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_simulator_session_unique_per_company_user(
    api_client: AsyncClient, authenticated_user_with_company: dict
):
    """Test that each company user has unique simulator session."""
    user = authenticated_user_with_company["user"]
    headers = authenticated_user_with_company["headers"]

    company1 = await Company.create(
        name="Company 1",
        description="Test",
        rules="",
        tone_of_voice="",
        assistant_name="AI",
        qualification_workflow="",
        qualification_examples="",
        collection_name="test1",
    )
    company2 = await Company.create(
        name="Company 2",
        description="Test",
        rules="",
        tone_of_voice="",
        assistant_name="AI",
        qualification_workflow="",
        qualification_examples="",
        collection_name="test2",
    )

    cu1 = await CompanyUser.create(user=user, company=company1, role=UserRole.ADMIN)
    cu2 = await CompanyUser.create(user=user, company=company2, role=UserRole.ADMIN)

    payload = {"text": "Company 1 message"}
    await api_client.post(
        f"/api/v1/companies/{company1.id}/simulator/message",
        headers=headers,
        json=payload,
    )

    payload = {"text": "Company 2 message"}
    await api_client.post(
        f"/api/v1/companies/{company2.id}/simulator/message",
        headers=headers,
        json=payload,
    )

    session1 = await SimulatorSession.filter(company_user=cu1).first()
    session2 = await SimulatorSession.filter(company_user=cu2).first()

    assert session1 is not None
    assert session2 is not None
    assert session1.id != session2.id

    user_msg1 = session1.messages[0]
    user_msg2 = session2.messages[0]
    assert user_msg1["content"] == "Company 1 message"
    assert user_msg2["content"] == "Company 2 message"
