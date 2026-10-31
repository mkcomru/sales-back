"""Router tests for the companies domain."""

import httpx
import pytest

from src.backend.modules.users.models import CompanyUser, User, UserRole


async def test_create_company_success(api_client: httpx.AsyncClient, company_payload, superuser_headers):
    payload = company_payload()
    response = await api_client.post("/api/v1/companies", json=payload, headers=superuser_headers)
    assert response.status_code == 201
    data = response.json()
    assert isinstance(data["id"], int)
    assert data["name"] == payload["name"]
    assert data["description"] == payload["description"]
    assert data["rules"] == payload["rules"]
    assert data["tone_of_voice"] == payload["tone_of_voice"]
    assert data["assistant_name"] == payload["assistant_name"]
    assert data["qualification_workflow"] == payload["qualification_workflow"]
    assert data["qualification_examples"] == payload["qualification_examples"]
    assert data["collection_name"] == payload["collection_name"]
    assert data["stages_config"] == payload["stages_config"]
    assert data["category_rules"] == payload["category_rules"]
    assert data["crm_forward_metadata_keys"] == payload["crm_forward_metadata_keys"]
    assert data["crm_default_stage_id"] == payload["crm_default_stage_id"]
    assert data["crm_manager_attention_stage_id"] == payload["crm_manager_attention_stage_id"]


async def test_create_company_validation_error(api_client: httpx.AsyncClient, superuser_headers):
    payload = {"name": "Test"}
    response = await api_client.post("/api/v1/companies", json=payload, headers=superuser_headers)
    assert response.status_code == 422


async def test_list_companies_superuser_sees_all(api_client: httpx.AsyncClient, company_payload, superuser_headers):
    """Superuser should see all companies."""
    payload1 = company_payload(name="Company 1")
    payload2 = company_payload(name="Company 2")
    await api_client.post("/api/v1/companies", json=payload1, headers=superuser_headers)
    await api_client.post("/api/v1/companies", json=payload2, headers=superuser_headers)
    response = await api_client.get("/api/v1/companies", headers=superuser_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    names = {item["name"] for item in data}
    assert "Company 1" in names
    assert "Company 2" in names


async def test_list_companies_regular_user_sees_only_theirs(
    api_client: httpx.AsyncClient,
    authenticated_user_with_company,
):
    """Regular user should see only their companies."""
    auth = authenticated_user_with_company
    response = await api_client.get("/api/v1/companies", headers=auth["headers"])
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == auth["company"].id
    assert data[0]["name"] == auth["company"].name


async def test_list_companies_regular_user_does_not_see_others(
    api_client: httpx.AsyncClient,
    company_factory,
    authenticated_user_with_company,
):
    """Regular user should not see companies they don't have access to."""
    auth = authenticated_user_with_company
    other_company = await company_factory(name="Other Company")

    response = await api_client.get("/api/v1/companies", headers=auth["headers"])
    assert response.status_code == 200
    data = response.json()
    company_ids = {item["id"] for item in data}
    assert auth["company"].id in company_ids
    assert other_company.id not in company_ids


async def test_list_companies_multiple_for_user(api_client: httpx.AsyncClient, company_factory, settings):
    """User with multiple companies should see all their companies."""
    from passlib.context import CryptContext

    from src.backend.modules.auth.service import AuthService
    from src.backend.modules.users.models import CompanyUser, User, UserRole

    company1 = await company_factory(name="Company 1")
    company2 = await company_factory(name="Company 2")
    company3 = await company_factory(name="Company 3")

    pwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=4, deprecated="auto")
    user = await User.create(
        first_name="Multi",
        last_name="Company",
        email="user_multi@test.com",
        hashed_password=pwd_context.hash("password"),
        is_active=True,
        is_superuser=False,
    )

    await CompanyUser.create(user=user, company=company1, role=UserRole.VIEWER)
    await CompanyUser.create(user=user, company=company2, role=UserRole.MANAGER)

    auth_service = AuthService(settings)
    token = auth_service.create_access_token(user.id, is_superuser=False)
    headers = {"Authorization": f"Bearer {token}"}

    response = await api_client.get("/api/v1/companies", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    company_ids = {item["id"] for item in data}
    assert company1.id in company_ids
    assert company2.id in company_ids
    assert company3.id not in company_ids


async def test_list_companies_requires_auth(api_client: httpx.AsyncClient):
    """Endpoint should require authentication."""
    response = await api_client.get("/api/v1/companies")
    assert response.status_code == 401


async def test_get_company_success(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id
    response = await api_client.get(f"/api/v1/companies/{company_id}", headers=auth["headers"])
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == company_id


async def test_get_company_not_found(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    response = await api_client.get("/api/v1/companies/99999", headers=auth["headers"])
    assert response.status_code == 404


async def test_update_company_success(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id
    update_payload = {"name": "Updated Name", "description": "Updated Description"}
    response = await api_client.patch(f"/api/v1/companies/{company_id}", json=update_payload, headers=auth["headers"])
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["description"] == "Updated Description"


async def test_update_company_partial(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id
    update_payload = {"name": "Only Name Updated"}
    response = await api_client.patch(f"/api/v1/companies/{company_id}", json=update_payload, headers=auth["headers"])
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Only Name Updated"


async def test_update_company_not_found(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    update_payload = {"name": "Updated Name"}
    response = await api_client.patch("/api/v1/companies/99999", json=update_payload, headers=auth["headers"])
    assert response.status_code == 404


async def test_delete_company_success(api_client: httpx.AsyncClient, company_factory, settings):
    from passlib.context import CryptContext

    from src.backend.modules.auth.service import AuthService
    from src.backend.modules.users.models import CompanyUser, User, UserRole

    company = await company_factory(name="Test Delete")

    pwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=4, deprecated="auto")
    owner_user = await User.create(
        first_name="Owner",
        last_name="User",
        email="owner@test.com",
        hashed_password=pwd_context.hash("owner_password"),
        is_active=True,
        is_superuser=False,
    )

    await CompanyUser.create(
        user=owner_user,
        company=company,
        role=UserRole.OWNER,
    )

    auth_service = AuthService(settings)
    owner_token = auth_service.create_access_token(owner_user.id, is_superuser=False)
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    response = await api_client.delete(f"/api/v1/companies/{company.id}", headers=owner_headers)
    assert response.status_code == 204


async def test_delete_company_not_found(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    response = await api_client.delete("/api/v1/companies/99999", headers=auth["headers"])
    assert response.status_code == 404


async def test_get_company_config_success(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id
    response = await api_client.get(f"/api/v1/companies/{company_id}/config", headers=auth["headers"])
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == company_id


async def test_get_company_config_not_found(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    response = await api_client.get("/api/v1/companies/99999/config", headers=auth["headers"])
    assert response.status_code == 404


async def test_get_company_specification_success(api_client: httpx.AsyncClient, service_headers, company):
    response = await api_client.get(
        f"/api/v1/internal/companies/{company.id}/specification",
        headers=service_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == company.id
    assert "categories" in data
    assert "products" in data
    assert "fields" in data
    assert "faqs" in data


async def test_get_company_specification_not_found(api_client: httpx.AsyncClient, service_headers):
    response = await api_client.get(
        "/api/v1/internal/companies/99999/specification",
        headers=service_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_company_managers_success(api_client: httpx.AsyncClient, company_factory, settings):
    """Admin should be able to get all managers of the company."""
    from passlib.context import CryptContext

    from src.backend.modules.auth.service import AuthService

    company = await company_factory(name="Test Managers Company")

    pwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=4, deprecated="auto")

    # Create admin user
    admin_user = await User.create(
        first_name="Admin",
        last_name="User",
        email="admin_managers@test.com",
        hashed_password=pwd_context.hash("password"),
        is_active=True,
        is_superuser=False,
    )
    await CompanyUser.create(user=admin_user, company=company, role=UserRole.ADMIN)

    # Create managers
    manager1 = await User.create(
        first_name="Manager",
        last_name="One",
        email="manager1@test.com",
        hashed_password=pwd_context.hash("password"),
        is_active=True,
    )
    await CompanyUser.create(user=manager1, company=company, role=UserRole.MANAGER)

    manager2 = await User.create(
        first_name="Manager",
        last_name="Two",
        email="manager2@test.com",
        hashed_password=pwd_context.hash("password"),
        is_active=True,
    )
    await CompanyUser.create(user=manager2, company=company, role=UserRole.MANAGER)

    # Create viewer (should not be in the list)
    viewer = await User.create(
        first_name="Viewer",
        last_name="User",
        email="viewer@test.com",
        hashed_password=pwd_context.hash("password"),
        is_active=True,
    )
    await CompanyUser.create(user=viewer, company=company, role=UserRole.VIEWER)

    auth_service = AuthService(settings)
    token = auth_service.create_access_token(admin_user.id, is_superuser=False)
    headers = {"Authorization": f"Bearer {token}"}

    response = await api_client.get(f"/api/v1/companies/{company.id}/managers", headers=headers)
    assert response.status_code == 200
    data = response.json()

    # Should return admin + 2 managers = 3 users
    assert len(data) == 3

    emails = {item["email"] for item in data}
    assert "admin_managers@test.com" in emails
    assert "manager1@test.com" in emails
    assert "manager2@test.com" in emails
    assert "viewer@test.com" not in emails

    # Check structure
    for manager in data:
        assert "id" in manager
        assert "user_id" in manager
        assert "first_name" in manager
        assert "last_name" in manager
        assert "email" in manager
        assert "role" in manager
        assert manager["role"] in ["admin", "manager", "owner"]


@pytest.mark.asyncio
async def test_get_company_managers_superuser_access(api_client: httpx.AsyncClient, company_factory, superuser_headers):
    """Superuser should be able to get managers of any company."""
    from passlib.context import CryptContext

    company = await company_factory(name="Test Superuser Managers")

    pwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=4, deprecated="auto")

    manager = await User.create(
        first_name="Manager",
        last_name="User",
        email="manager_super@test.com",
        hashed_password=pwd_context.hash("password"),
        is_active=True,
    )
    await CompanyUser.create(user=manager, company=company, role=UserRole.MANAGER)

    response = await api_client.get(f"/api/v1/companies/{company.id}/managers", headers=superuser_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_get_company_managers_forbidden_for_viewer(api_client: httpx.AsyncClient, company_factory, settings):
    """Viewer should not be able to get managers list."""
    from passlib.context import CryptContext

    from src.backend.modules.auth.service import AuthService

    company = await company_factory(name="Test Forbidden Managers")

    pwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=4, deprecated="auto")

    viewer_user = await User.create(
        first_name="Viewer",
        last_name="User",
        email="viewer_forbidden@test.com",
        hashed_password=pwd_context.hash("password"),
        is_active=True,
        is_superuser=False,
    )
    await CompanyUser.create(user=viewer_user, company=company, role=UserRole.VIEWER)

    auth_service = AuthService(settings)
    token = auth_service.create_access_token(viewer_user.id, is_superuser=False)
    headers = {"Authorization": f"Bearer {token}"}

    response = await api_client.get(f"/api/v1/companies/{company.id}/managers", headers=headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_company_managers_forbidden_for_manager(api_client: httpx.AsyncClient, company_factory, settings):
    """Manager should not be able to get managers list (only ADMIN+)."""
    from passlib.context import CryptContext

    from src.backend.modules.auth.service import AuthService

    company = await company_factory(name="Test Manager Forbidden")

    pwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=4, deprecated="auto")

    manager_user = await User.create(
        first_name="Manager",
        last_name="User",
        email="manager_forbidden@test.com",
        hashed_password=pwd_context.hash("password"),
        is_active=True,
        is_superuser=False,
    )
    await CompanyUser.create(user=manager_user, company=company, role=UserRole.MANAGER)

    auth_service = AuthService(settings)
    token = auth_service.create_access_token(manager_user.id, is_superuser=False)
    headers = {"Authorization": f"Bearer {token}"}

    response = await api_client.get(f"/api/v1/companies/{company.id}/managers", headers=headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_company_managers_not_found(api_client: httpx.AsyncClient, superuser_headers):
    """Should return 404 for non-existent company."""
    response = await api_client.get("/api/v1/companies/99999/managers", headers=superuser_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_company_managers_requires_auth(api_client: httpx.AsyncClient, company_factory):
    """Endpoint should require authentication."""
    company = await company_factory(name="Test Auth Required")
    response = await api_client.get(f"/api/v1/companies/{company.id}/managers")
    assert response.status_code == 401
