"""Model tests for FAQs."""

import pytest
from tortoise.exceptions import IntegrityError, ValidationError

from src.backend.modules.companies.models import FAQ


async def test_faq_required_fields():
    with pytest.raises((ValidationError, IntegrityError)):
        await FAQ.create()


async def test_faq_company_required():
    with pytest.raises((ValidationError, IntegrityError)):
        await FAQ.create(
            category="General",
            question="Question?",
            answer="Answer",
        )


async def test_faq_category_required(company_factory):
    company = await company_factory()
    with pytest.raises(ValidationError):
        await FAQ.create(
            company=company,
            question="Question?",
            answer="Answer",
        )


async def test_faq_question_required(company_factory):
    company = await company_factory()
    with pytest.raises(IntegrityError):
        await FAQ.create(
            company=company,
            category="General",
            answer="Answer",
        )


async def test_faq_answer_required(company_factory):
    company = await company_factory()
    with pytest.raises(IntegrityError):
        await FAQ.create(
            company=company,
            category="General",
            question="Question?",
        )


async def test_faq_keywords_default(company_factory):
    company = await company_factory()
    faq = await FAQ.create(
        company=company,
        category="General",
        question="Question?",
        answer="Answer",
    )
    assert faq.keywords == []


async def test_faq_keywords_persists(company_factory):
    company = await company_factory()
    keywords = ["keyword1", "keyword2"]
    faq = await FAQ.create(
        company=company,
        category="General",
        question="Question?",
        answer="Answer",
        keywords=keywords,
    )
    assert faq.keywords == keywords
    faq.keywords = ["updated"]
    await faq.save()
    refreshed = await FAQ.get(id=faq.id)
    assert refreshed.keywords == ["updated"]


async def test_faq_category_max_length(company_factory):
    company = await company_factory()
    long_category = "a" * 256
    with pytest.raises(ValidationError):
        await FAQ.create(
            company=company,
            category=long_category,
            question="Question?",
            answer="Answer",
        )
