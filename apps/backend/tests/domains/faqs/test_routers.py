"""Router tests for FAQs."""

import httpx


async def test_list_faqs_empty(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id
    response = await api_client.get(f"/api/v1/companies/{company_id}/faqs", headers=auth["headers"])
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


async def test_list_faqs_with_data(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    faq1 = {
        "category": "General",
        "question": "Question 1?",
        "answer": "Answer 1",
        "keywords": ["keyword1"],
    }
    faq2 = {
        "category": "Support",
        "question": "Question 2?",
        "answer": "Answer 2",
        "keywords": ["keyword2"],
    }
    await api_client.post(f"/api/v1/companies/{company_id}/faqs", json=faq1, headers=auth["headers"])
    await api_client.post(f"/api/v1/companies/{company_id}/faqs", json=faq2, headers=auth["headers"])

    response = await api_client.get(f"/api/v1/companies/{company_id}/faqs", headers=auth["headers"])
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    questions = {item["question"] for item in data["items"]}
    assert "Question 1?" in questions
    assert "Question 2?" in questions


async def test_create_faq_success(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    payload = {
        "category": "General",
        "question": "What is this?",
        "answer": "This is a test FAQ",
        "keywords": ["test", "faq"],
    }
    response = await api_client.post(f"/api/v1/companies/{company_id}/faqs", json=payload, headers=auth["headers"])
    assert response.status_code == 201
    data = response.json()
    assert isinstance(data["id"], int)
    assert data["category"] == payload["category"]
    assert data["question"] == payload["question"]
    assert data["answer"] == payload["answer"]
    assert data["keywords"] == payload["keywords"]


async def test_create_faq_default_keywords(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    payload = {
        "category": "General",
        "question": "Question?",
        "answer": "Answer",
    }
    response = await api_client.post(f"/api/v1/companies/{company_id}/faqs", json=payload, headers=auth["headers"])
    assert response.status_code == 201
    data = response.json()
    assert data["keywords"] == []


async def test_create_faq_validation_error(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    response = await api_client.post(f"/api/v1/companies/{company_id}/faqs", json={}, headers=auth["headers"])
    assert response.status_code == 422


async def test_get_faq_success(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    payload = {
        "category": "General",
        "question": "Get FAQ?",
        "answer": "Answer",
    }
    create_resp = await api_client.post(f"/api/v1/companies/{company_id}/faqs", json=payload, headers=auth["headers"])
    faq_id = create_resp.json()["id"]

    response = await api_client.get(f"/api/v1/companies/{company_id}/faqs/{faq_id}", headers=auth["headers"])
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == faq_id
    assert data["question"] == payload["question"]


async def test_get_faq_not_found(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    response = await api_client.get(f"/api/v1/companies/{company_id}/faqs/99999", headers=auth["headers"])
    assert response.status_code == 404


async def test_get_faq_wrong_company(api_client: httpx.AsyncClient, company_factory, settings):
    from passlib.context import CryptContext

    from src.backend.modules.auth.service import AuthService
    from src.backend.modules.users.models import CompanyUser, User, UserRole

    company1 = await company_factory(name="Company 1")
    company2 = await company_factory(name="Company 2")

    pwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=4, deprecated="auto")
    user = await User.create(
        first_name="Test",
        last_name="User",
        email="user@test.com",
        hashed_password=pwd_context.hash("password"),
        is_active=True,
        is_superuser=False,
    )

    await CompanyUser.create(user=user, company=company1, role=UserRole.ADMIN)
    await CompanyUser.create(user=user, company=company2, role=UserRole.ADMIN)

    auth_service = AuthService(settings)
    token = auth_service.create_access_token(user.id, is_superuser=False)
    headers = {"Authorization": f"Bearer {token}"}

    payload = {"category": "General", "question": "Q?", "answer": "A"}
    create_resp = await api_client.post(f"/api/v1/companies/{company1.id}/faqs", json=payload, headers=headers)
    faq_id = create_resp.json()["id"]

    response = await api_client.get(f"/api/v1/companies/{company2.id}/faqs/{faq_id}", headers=headers)
    assert response.status_code == 404


async def test_update_faq_success(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    payload = {
        "category": "General",
        "question": "Original?",
        "answer": "Original",
    }
    create_resp = await api_client.post(f"/api/v1/companies/{company_id}/faqs", json=payload, headers=auth["headers"])
    faq_id = create_resp.json()["id"]

    update_payload = {"question": "Updated?", "answer": "Updated"}
    response = await api_client.patch(
        f"/api/v1/companies/{company_id}/faqs/{faq_id}",
        json=update_payload,
        headers=auth["headers"],
    )
    assert response.status_code == 200
    data = response.json()
    assert data["question"] == "Updated?"
    assert data["answer"] == "Updated"
    assert data["category"] == payload["category"]


async def test_update_faq_keywords(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    payload = {
        "category": "General",
        "question": "Q?",
        "answer": "A",
        "keywords": ["old"],
    }
    create_resp = await api_client.post(f"/api/v1/companies/{company_id}/faqs", json=payload, headers=auth["headers"])
    faq_id = create_resp.json()["id"]

    update_payload = {"keywords": ["new", "updated"]}
    response = await api_client.patch(
        f"/api/v1/companies/{company_id}/faqs/{faq_id}",
        json=update_payload,
        headers=auth["headers"],
    )
    assert response.status_code == 200
    data = response.json()
    assert data["keywords"] == ["new", "updated"]


async def test_update_faq_not_found(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    update_payload = {"question": "Updated?"}
    response = await api_client.patch(
        f"/api/v1/companies/{company_id}/faqs/99999",
        json=update_payload,
        headers=auth["headers"],
    )
    assert response.status_code == 404


async def test_delete_faq_success(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    payload = {
        "category": "General",
        "question": "Delete FAQ?",
        "answer": "Answer",
    }
    create_resp = await api_client.post(f"/api/v1/companies/{company_id}/faqs", json=payload, headers=auth["headers"])
    faq_id = create_resp.json()["id"]

    response = await api_client.delete(f"/api/v1/companies/{company_id}/faqs/{faq_id}", headers=auth["headers"])
    assert response.status_code == 204

    get_response = await api_client.get(f"/api/v1/companies/{company_id}/faqs/{faq_id}", headers=auth["headers"])
    assert get_response.status_code == 404


async def test_delete_faq_not_found(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    response = await api_client.delete(f"/api/v1/companies/{company_id}/faqs/99999", headers=auth["headers"])
    assert response.status_code == 404


async def test_search_faqs_empty(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    response = await api_client.get(
        f"/api/v1/companies/{company_id}/faqs/search",
        params={"q": "nonexistent"},
        headers=auth["headers"],
    )
    assert response.status_code == 200
    assert response.json() == []


async def test_search_faqs_with_results(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    faq1 = {
        "category": "General",
        "question": "How to test?",
        "answer": "Answer",
    }
    faq2 = {
        "category": "Support",
        "question": "Other question?",
        "answer": "Answer",
    }
    await api_client.post(f"/api/v1/companies/{company_id}/faqs", json=faq1, headers=auth["headers"])
    await api_client.post(f"/api/v1/companies/{company_id}/faqs", json=faq2, headers=auth["headers"])

    response = await api_client.get(
        f"/api/v1/companies/{company_id}/faqs/search",
        params={"q": "test"},
        headers=auth["headers"],
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert "test" in data[0]["question"].lower()
