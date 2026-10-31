"""Service tests for FAQs."""

import pytest

from src.backend.modules.companies.exceptions import FAQNotFoundError
from src.backend.modules.companies.models import FAQ
from src.backend.modules.companies.schemas import FAQPatch, FAQRequest
from src.backend.modules.companies.service import FAQsService


async def test_service_list_faqs_empty(company_factory):
    company = await company_factory()
    service = FAQsService()
    faqs = await service.list_faqs(company.id)
    assert faqs == []


async def test_service_list_faqs_with_data(company_factory):
    company = await company_factory()
    await FAQ.create(
        company=company,
        category="General",
        question="Q1?",
        answer="A1",
    )
    await FAQ.create(
        company=company,
        category="Support",
        question="Q2?",
        answer="A2",
    )

    service = FAQsService()
    faqs = await service.list_faqs(company.id)
    assert len(faqs) == 2
    assert all(hasattr(f, "id") for f in faqs)


async def test_service_get_faq_success(company_factory):
    company = await company_factory()
    faq = await FAQ.create(
        company=company,
        category="General",
        question="Test Question?",
        answer="Answer",
    )

    service = FAQsService()
    found = await service.get_faq(faq.id, company.id)
    assert found.id == faq.id
    assert found.question == "Test Question?"


async def test_service_get_faq_not_found(company_factory):
    company = await company_factory()
    service = FAQsService()
    with pytest.raises(FAQNotFoundError):
        await service.get_faq(99999, company.id)


async def test_service_get_faq_wrong_company(company_factory):
    company1 = await company_factory(name="Company 1")
    company2 = await company_factory(name="Company 2")

    faq = await FAQ.create(
        company=company1,
        category="General",
        question="Q?",
        answer="A",
    )

    service = FAQsService()
    with pytest.raises(FAQNotFoundError):
        await service.get_faq(faq.id, company2.id)


async def test_service_create_faq_success(company_factory):
    company = await company_factory()
    service = FAQsService()

    payload = FAQRequest(
        category="General",
        question="New Question?",
        answer="New Answer",
        keywords=["test"],
    )
    faq = await service.create_faq(company.id, payload)

    assert faq.question == "New Question?"
    assert faq.category == "General"
    assert faq.keywords == ["test"]
    assert isinstance(faq.id, int)


async def test_service_update_faq_success(company_factory):
    company = await company_factory()
    faq = await FAQ.create(
        company=company,
        category="General",
        question="Original?",
        answer="Original",
    )

    service = FAQsService()
    payload = FAQPatch(question="Updated?", answer="Updated")
    updated = await service.update_faq(faq.id, company.id, payload)

    assert updated.question == "Updated?"
    assert updated.answer == "Updated"


async def test_service_update_faq_not_found(company_factory):
    company = await company_factory()
    service = FAQsService()
    payload = FAQPatch(question="Updated?")
    with pytest.raises(FAQNotFoundError):
        await service.update_faq(99999, company.id, payload)


async def test_service_delete_faq_success(company_factory):
    company = await company_factory()
    faq = await FAQ.create(
        company=company,
        category="General",
        question="Delete Me?",
        answer="Answer",
    )

    service = FAQsService()
    deleted = await service.delete_faq(faq.id, company.id)
    assert deleted is True

    with pytest.raises(FAQNotFoundError):
        await service.get_faq(faq.id, company.id)


async def test_service_delete_faq_not_found(company_factory):
    company = await company_factory()
    service = FAQsService()
    with pytest.raises(FAQNotFoundError):
        await service.delete_faq(99999, company.id)


async def test_service_search_faqs(company_factory):
    company = await company_factory()
    await FAQ.create(
        company=company,
        category="General",
        question="How to test?",
        answer="Answer",
    )
    await FAQ.create(
        company=company,
        category="Support",
        question="Other question?",
        answer="Answer",
    )

    service = FAQsService()
    results = await service.search_faqs(company.id, "test")
    assert len(results) == 1
    assert "test" in results[0].question.lower()
