"""Model tests for fields."""

import pytest
from tortoise.exceptions import IntegrityError, ValidationError

from src.backend.modules.fields.models import AnswerType, Field


async def test_field_required_fields():
    with pytest.raises(ValidationError):
        await Field.create()


async def test_field_name_required(company_factory):
    company = await company_factory()
    with pytest.raises(ValidationError):
        await Field.create(
            company=company,
            question="Question?",
            answer_type=AnswerType.STRING,
        )


async def test_field_question_required(company_factory):
    company = await company_factory()
    with pytest.raises(IntegrityError):
        await Field.create(
            company=company,
            name="Test",
            answer_type=AnswerType.STRING,
        )


async def test_field_answer_type_required(company_factory):
    company = await company_factory()
    with pytest.raises(ValidationError):
        await Field.create(
            company=company,
            name="Test",
            question="Question?",
        )


async def test_field_company_required():
    with pytest.raises((ValidationError, IntegrityError)):
        await Field.create(
            name="Test",
            question="Question?",
            answer_type=AnswerType.STRING,
        )


async def test_field_required_default(company_factory):
    company = await company_factory()
    field = await Field.create(
        company=company,
        name="Test",
        question="Question?",
        answer_type=AnswerType.STRING,
    )
    assert field.required is False


async def test_field_answer_type_enum(company_factory):
    company = await company_factory()
    for answer_type in AnswerType:
        field = await Field.create(
            company=company,
            name=f"Field {answer_type.value}",
            question="Question?",
            answer_type=answer_type,
        )
        assert field.answer_type == answer_type


async def test_field_category_nullable(company_factory):
    company = await company_factory()
    field = await Field.create(
        company=company,
        name="Test",
        question="Question?",
        answer_type=AnswerType.STRING,
        category=None,
    )
    assert field.category is None


async def test_field_product_nullable(company_factory):
    company = await company_factory()
    field = await Field.create(
        company=company,
        name="Test",
        question="Question?",
        answer_type=AnswerType.STRING,
        product=None,
    )
    assert field.product is None


async def test_field_name_max_length(company_factory):
    company = await company_factory()
    long_name = "a" * 256
    with pytest.raises(ValidationError):
        await Field.create(
            company=company,
            name=long_name,
            question="Question?",
            answer_type=AnswerType.STRING,
        )
