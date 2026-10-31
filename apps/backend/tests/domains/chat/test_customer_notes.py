"""Tests for customer notes functionality."""

import pytest

from src.backend.modules.chat.models import Customer
from src.backend.modules.chat.repository import CustomersRepository


class TestCustomerNotesRepository:
    """Tests for CustomersRepository.update_notes()."""

    @pytest.mark.asyncio
    async def test_update_notes_success(self, customer: Customer):
        """Test successful notes update."""
        repo = CustomersRepository()

        notes_text = "Important client. Prefers email communication."
        updated_customer = await repo.update_notes(customer, notes_text)

        assert updated_customer.notes == notes_text
        assert updated_customer.id == customer.id

    @pytest.mark.asyncio
    async def test_update_notes_clear(self, customer: Customer):
        """Test clearing notes with None."""
        repo = CustomersRepository()

        # Set notes first
        await repo.update_notes(customer, "Some notes")
        assert customer.notes == "Some notes"

        # Clear notes
        updated_customer = await repo.update_notes(customer, None)

        assert updated_customer.notes is None

    @pytest.mark.asyncio
    async def test_update_notes_empty_string(self, customer: Customer):
        """Test updating notes with empty string."""
        repo = CustomersRepository()

        updated_customer = await repo.update_notes(customer, "")

        assert updated_customer.notes == ""

    @pytest.mark.asyncio
    async def test_update_notes_long_text(self, customer: Customer):
        """Test updating notes with long text."""
        repo = CustomersRepository()

        long_notes = "A" * 5000  # Long text
        updated_customer = await repo.update_notes(customer, long_notes)

        assert updated_customer.notes == long_notes
        assert len(updated_customer.notes) == 5000

    @pytest.mark.asyncio
    async def test_update_notes_unicode(self, customer: Customer):
        """Test updating notes with unicode characters."""
        repo = CustomersRepository()

        unicode_notes = "Заметки: 🔥 Важный клиент! 中文 عربي"
        updated_customer = await repo.update_notes(customer, unicode_notes)

        assert updated_customer.notes == unicode_notes


class TestCustomerNotesService:
    """Tests for ChatService.update_customer_notes()."""

    @pytest.mark.asyncio
    async def test_update_customer_notes_success(self, customer: Customer, chat_service):
        """Test successful customer notes update through service."""
        service = chat_service

        notes_text = "VIP client, handle with priority."
        updated_customer = await service.update_customer_notes(
            customer_id=customer.id,
            notes=notes_text,
        )

        assert updated_customer.notes == notes_text
        assert updated_customer.id == customer.id

    @pytest.mark.asyncio
    async def test_update_customer_notes_clear(self, customer: Customer, chat_service):
        """Test clearing customer notes."""
        service = chat_service

        # Set notes first
        await service.update_customer_notes(customer.id, "Initial notes")

        # Clear notes
        updated_customer = await service.update_customer_notes(customer.id, None)

        assert updated_customer.notes is None

    @pytest.mark.asyncio
    async def test_update_customer_notes_not_found(self, chat_service):
        """Test updating notes for non-existent customer."""
        service = chat_service

        with pytest.raises(ValueError, match="Customer 99999 not found"):
            await service.update_customer_notes(
                customer_id=99999,
                notes="Some notes",
            )

    @pytest.mark.asyncio
    async def test_update_customer_notes_multiple_times(self, customer: Customer, chat_service):
        """Test updating notes multiple times."""
        service = chat_service

        # First update
        await service.update_customer_notes(customer.id, "First version")
        customer_v1 = await Customer.get(id=customer.id)
        assert customer_v1.notes == "First version"

        # Second update
        await service.update_customer_notes(customer.id, "Second version")
        customer_v2 = await Customer.get(id=customer.id)
        assert customer_v2.notes == "Second version"

        # Third update
        await service.update_customer_notes(customer.id, "Final version")
        customer_v3 = await Customer.get(id=customer.id)
        assert customer_v3.notes == "Final version"


class TestCustomerNotesAPI:
    """Tests for customer notes API endpoint."""

    @pytest.mark.asyncio
    async def test_update_customer_notes_success(self, api_client, customer: Customer, manager_headers: dict[str, str]):
        """Test successful customer notes update via API."""
        notes_text = "Key account manager: John Doe"

        response = await api_client.patch(
            f"/api/v1/companies/{customer.company_id}/customers/{customer.id}/notes",
            json={"notes": notes_text},
            headers=manager_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["customer_id"] == customer.id
        assert data["user_id"] == customer.user_id
        assert data["notes"] == notes_text
        assert "updated_at" in data

        # Verify in database
        updated_customer = await Customer.get(id=customer.id)
        assert updated_customer.notes == notes_text

    @pytest.mark.asyncio
    async def test_update_customer_notes_clear(self, api_client, customer: Customer, manager_headers: dict[str, str]):
        """Test clearing customer notes via API."""
        # Set notes first
        customer.notes = "Initial notes"
        await customer.save()

        response = await api_client.patch(
            f"/api/v1/companies/{customer.company_id}/customers/{customer.id}/notes",
            json={"notes": None},
            headers=manager_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["notes"] is None

        # Verify in database
        updated_customer = await Customer.get(id=customer.id)
        assert updated_customer.notes is None

    @pytest.mark.asyncio
    async def test_update_customer_notes_without_body(
        self, api_client, customer: Customer, manager_headers: dict[str, str]
    ):
        """Test updating notes without request body."""
        response = await api_client.patch(
            f"/api/v1/companies/{customer.company_id}/customers/{customer.id}/notes",
            headers=manager_headers,
        )

        assert response.status_code == 400
        assert "Request body is required" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_customer_notes_unauthorized(self, api_client, customer: Customer):
        """Test updating notes without authorization."""
        response = await api_client.patch(
            f"/api/v1/companies/{customer.company_id}/customers/{customer.id}/notes",
            json={"notes": "Unauthorized attempt"},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_update_customer_notes_wrong_company(
        self, api_client, customer: Customer, company_factory, manager_headers: dict[str, str]
    ):
        """Test updating notes for customer from different company."""
        # Create another company
        other_company = await company_factory(name="Other Company")

        response = await api_client.patch(
            f"/api/v1/companies/{other_company.id}/customers/{customer.id}/notes",
            json={"notes": "Should fail"},
            headers=manager_headers,
        )

        # Should get 403 because user doesn't have access to this company
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_update_customer_notes_not_found(
        self, api_client, customer: Customer, manager_headers: dict[str, str]
    ):
        """Test updating notes for non-existent customer."""
        response = await api_client.patch(
            f"/api/v1/companies/{customer.company_id}/customers/99999/notes",
            json={"notes": "Non-existent"},
            headers=manager_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_customer_notes_empty_string(
        self, api_client, customer: Customer, manager_headers: dict[str, str]
    ):
        """Test updating notes with empty string."""
        response = await api_client.patch(
            f"/api/v1/companies/{customer.company_id}/customers/{customer.id}/notes",
            json={"notes": ""},
            headers=manager_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["notes"] == ""

    @pytest.mark.asyncio
    async def test_update_customer_notes_long_text(
        self, api_client, customer: Customer, manager_headers: dict[str, str]
    ):
        """Test updating notes with very long text."""
        long_notes = "Important: " + "A" * 10000

        response = await api_client.patch(
            f"/api/v1/companies/{customer.company_id}/customers/{customer.id}/notes",
            json={"notes": long_notes},
            headers=manager_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["notes"] == long_notes

    @pytest.mark.asyncio
    async def test_get_customer_detail_includes_notes(
        self, api_client, customer: Customer, manager_headers: dict[str, str]
    ):
        """Test that GET customer endpoint returns notes field."""
        # Set notes
        customer.notes = "Customer notes for display"
        await customer.save()

        response = await api_client.get(
            f"/api/v1/companies/{customer.company_id}/customers/{customer.id}",
            headers=manager_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "notes" in data
        assert data["notes"] == "Customer notes for display"

    @pytest.mark.asyncio
    async def test_get_customer_detail_notes_null(
        self, api_client, customer: Customer, manager_headers: dict[str, str]
    ):
        """Test that GET customer endpoint returns null for empty notes."""
        # Ensure notes are null
        customer.notes = None
        await customer.save()

        response = await api_client.get(
            f"/api/v1/companies/{customer.company_id}/customers/{customer.id}",
            headers=manager_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "notes" in data
        assert data["notes"] is None

    @pytest.mark.asyncio
    async def test_update_customer_notes_special_characters(
        self, api_client, customer: Customer, manager_headers: dict[str, str]
    ):
        """Test updating notes with special characters and formatting."""
        special_notes = """Multi-line notes:
- Point 1: Important client
- Point 2: Requires follow-up
- Contact: email@example.com
- Phone: +1-234-567-8900

Special chars: <>&"'`\n\t"""

        response = await api_client.patch(
            f"/api/v1/companies/{customer.company_id}/customers/{customer.id}/notes",
            json={"notes": special_notes},
            headers=manager_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["notes"] == special_notes

        # Verify roundtrip
        get_response = await api_client.get(
            f"/api/v1/companies/{customer.company_id}/customers/{customer.id}",
            headers=manager_headers,
        )
        assert get_response.json()["notes"] == special_notes
