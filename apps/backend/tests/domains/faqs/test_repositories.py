"""Repository tests for FAQs."""

from src.backend.modules.companies.models import FAQ
from src.backend.modules.companies.repository import FAQsRepository


async def test_repository_list_by_company_empty(company_factory):
    company = await company_factory()
    repo = FAQsRepository()
    faqs = await repo.list_by_company(company.id)
    assert faqs == []


async def test_repository_list_by_company_with_data(company_factory):
    company1 = await company_factory(name="Company 1")
    company2 = await company_factory(name="Company 2")

    await FAQ.create(
        company=company1,
        category="General",
        question="Q1?",
        answer="A1",
    )
    await FAQ.create(
        company=company1,
        category="Support",
        question="Q2?",
        answer="A2",
    )
    await FAQ.create(
        company=company2,
        category="General",
        question="Q3?",
        answer="A3",
    )

    repo = FAQsRepository()
    company1_faqs = await repo.list_by_company(company1.id)
    assert len(company1_faqs) == 2
    questions = {f.question for f in company1_faqs}
    assert "Q1?" in questions
    assert "Q2?" in questions


async def test_repository_get_by_id_success(company_factory):
    company = await company_factory()
    faq = await FAQ.create(
        company=company,
        category="General",
        question="Test Question?",
        answer="Answer",
    )

    repo = FAQsRepository()
    found = await repo.get_by_id(faq.id)
    assert found is not None
    assert found.id == faq.id
    assert found.question == "Test Question?"


async def test_repository_get_by_id_not_found():
    repo = FAQsRepository()
    found = await repo.get_by_id(99999)
    assert found is None


async def test_repository_create_faq_success(company_factory):
    company = await company_factory()
    repo = FAQsRepository()

    faq = await repo.create_faq(
        company_id=company.id,
        category="General",
        question="New Question?",
        answer="New Answer",
        keywords=["test"],
    )

    assert faq.id is not None
    assert faq.question == "New Question?"
    assert faq.company_id == company.id
    assert faq.keywords == ["test"]


async def test_repository_create_faq_default_keywords(company_factory):
    company = await company_factory()
    repo = FAQsRepository()

    faq = await repo.create_faq(
        company_id=company.id,
        category="General",
        question="Q?",
        answer="A",
    )
    assert faq.keywords == []


async def test_repository_update_faq_success(company_factory):
    company = await company_factory()
    faq = await FAQ.create(
        company=company,
        category="General",
        question="Original?",
        answer="Original",
    )

    repo = FAQsRepository()
    updated = await repo.update_faq(faq.id, {"question": "Updated?", "answer": "Updated"})
    assert updated is not None
    assert updated.question == "Updated?"
    assert updated.answer == "Updated"


async def test_repository_update_faq_not_found():
    repo = FAQsRepository()
    updated = await repo.update_faq(99999, {"question": "Updated?"})
    assert updated is None


async def test_repository_delete_faq_success(company_factory):
    company = await company_factory()
    faq = await FAQ.create(
        company=company,
        category="General",
        question="Delete FAQ?",
        answer="Answer",
    )

    repo = FAQsRepository()
    deleted = await repo.delete_faq(faq.id)
    assert deleted is True
    found = await FAQ.get_or_none(id=faq.id)
    assert found is None


async def test_repository_delete_faq_not_found():
    repo = FAQsRepository()
    deleted = await repo.delete_faq(99999)
    assert deleted is False


async def test_repository_search_by_keywords(company_factory):
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

    repo = FAQsRepository()
    results = await repo.search_by_keywords(company.id, "test")
    assert len(results) == 1
    assert "test" in results[0].question.lower()
