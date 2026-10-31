"""Service-layer tests for stages."""

import pytest

from src.backend.core.conditions.exceptions import ConditionSyntaxError
from src.backend.modules.stages.models import StageTemplate


@pytest.mark.asyncio
async def test_create_default_stages(company_without_stages, stages_service):
    """Test create_default_stages creates 2 default stages."""
    stages = await stages_service.create_default_stages(company_without_stages.id)

    assert len(stages) == 2

    # Check names
    names = [s.name for s in stages]
    assert "Новый" in names
    assert "Закрыто" in names

    # Check first stage
    first_stage = next(s for s in stages if s.position == 0)
    assert first_stage.name == "Новый"
    assert first_stage.transition_condition == {"$any": True}
    assert first_stage.is_system is True
    assert first_stage.is_final is False

    # Check final stage
    final_stage = next(s for s in stages if s.is_final)
    assert final_stage.name == "Закрыто"
    assert final_stage.is_system is True
    assert final_stage.auto_close is True


@pytest.mark.asyncio
async def test_create_default_stages_called_on_company_creation(test_superuser):
    """Test that default stages are created when company is created."""
    from src.backend.modules.companies.service import CompaniesService

    companies_service = CompaniesService()
    company = await companies_service.create_company(
        creator_id=test_superuser.id,
        name="Test Company",
        description="Test",
        rules="Rules",
        tone_of_voice="Professional",
        assistant_name="Assistant",
        qualification_workflow="Workflow",
        qualification_examples="Examples",
        collection_name="test_collection",
    )

    # Check stages were created
    stages = await StageTemplate.filter(company_id=company.id).all()
    assert len(stages) == 2


@pytest.mark.asyncio
async def test_validate_condition_valid(stages_service):
    """Test validation passes for valid condition."""
    valid_condition = {
        "$and": [
            {"order_fields.budget": {"$gte": 1000}},
            {"customer_fields.city": {"$exists": True}},
        ]
    }

    # Should not raise
    from src.backend.core.conditions import validate_condition

    result = validate_condition(valid_condition)
    assert result is None  # No return value


@pytest.mark.asyncio
async def test_validate_condition_invalid_operator(stages_service):
    """Test validation fails for invalid operator."""
    from src.backend.core.conditions import validate_condition

    invalid_condition = {"$invalid_op": True}

    with pytest.raises(ConditionSyntaxError):
        validate_condition(invalid_condition)


@pytest.mark.asyncio
async def test_validate_condition_invalid_structure(stages_service):
    """Test validation fails for invalid structure."""
    from src.backend.core.conditions import validate_condition

    invalid_condition = {"$and": "not_a_list"}

    with pytest.raises(ConditionSyntaxError):
        validate_condition(invalid_condition)


@pytest.mark.asyncio
async def test_validate_condition_none(stages_service):
    """Test validation passes for None (no condition)."""
    from src.backend.core.conditions import validate_condition

    result = validate_condition(None)
    assert result is None


@pytest.mark.asyncio
async def test_create_stage_validates_condition(company_without_stages, stages_service):
    """Test create_stage validates transition_condition."""
    with pytest.raises(ValueError, match="Invalid transition_condition"):
        await stages_service.create_stage(
            company_id=company_without_stages.id,
            name="Invalid Stage",
            transition_condition={"$bad_operator": True},
        )


@pytest.mark.asyncio
async def test_update_stage_validates_condition(company_without_stages, stages_service, stage_template):
    """Test update_stage validates transition_condition."""
    with pytest.raises(ValueError, match="Invalid transition_condition"):
        await stages_service.update_stage(
            stage=stage_template,
            transition_condition={"$invalid": "value"},
        )


@pytest.mark.asyncio
async def test_create_stage_with_is_final_success(company, stages_service):
    """Test creating final stage succeeds (no result field required)."""
    stage = await stages_service.create_stage(
        company_id=company.id,
        name="Final Stage",
        is_final=True,
    )
    assert stage.name == "Final Stage"
    assert stage.is_final is True
    assert stage.result is None


@pytest.mark.asyncio
async def test_create_stage_with_auto_close_requires_is_final(company, stages_service):
    """Test auto_close requires is_final=True."""
    with pytest.raises(ValueError, match="final"):
        await stages_service.create_stage(
            company_id=company.id,
            name="Auto Close Stage",
            auto_close=True,
            is_final=False,
        )


@pytest.mark.asyncio
async def test_list_by_company(company_without_stages, stage_templates, stages_service):
    """Test list_by_company returns stages sorted by position."""
    stages = await stages_service.stages_repo.list_by_company(company_without_stages.id)

    assert len(stages) == 5

    # Check sorted
    positions = [s.position for s in stages]
    assert positions == sorted(positions)


@pytest.mark.asyncio
async def test_reorder_stages(company_without_stages, stage_templates, stages_service):
    """Test reorder_stages updates positions."""
    # Reverse order
    new_order = [s.id for s in reversed(stage_templates)]

    await stages_service.reorder_stages(company_without_stages.id, new_order)

    # Verify
    stages = await stages_service.stages_repo.list_by_company(company_without_stages.id)

    # First should be what was last
    assert stages[0].id == stage_templates[4].id
    assert stages[0].position == 0

    # Last should be what was first
    assert stages[4].id == stage_templates[0].id
    assert stages[4].position == 4


@pytest.mark.asyncio
async def test_reorder_stages_with_missing_id(company, stage_templates, stages_service):
    """Test reorder with non-existent ID raises error."""
    with pytest.raises(ValueError, match="not found"):
        await stages_service.reorder_stages(company.id, [99999, stage_templates[0].id])


@pytest.mark.asyncio
async def test_recalculate_company_orders_stages(company_without_stages, stage_templates, stages_service):
    """Test recalculate_company_orders_stages triggers recalculation for all orders."""
    from src.backend.modules.chat.models import Customer
    from src.backend.modules.orders.service import OrderService

    # Create orders
    customer = await Customer.create(
        user_id="test-recalc",
        company_id=company_without_stages.id,
        name="Test",
        meta={},
    )

    order_service = OrderService()
    order1 = await order_service.create_order(
        company_id=company_without_stages.id,
        customer_id=customer.id,
    )
    order2 = await order_service.create_order(
        company_id=company_without_stages.id,
        customer_id=customer.id,
    )

    # Both should be on first stage
    await order1.refresh_from_db()
    await order2.refresh_from_db()
    assert order1.stage_id == stage_templates[0].id
    assert order2.stage_id == stage_templates[0].id

    # Update order1 fields to trigger transition
    await order_service.update_order_fields(
        order1.id,
        {"budget": 2000},
    )

    await order1.refresh_from_db()
    # order1 should be on second stage now
    assert order1.stage_id == stage_templates[1].id

    # order2 should still be on first stage
    await order2.refresh_from_db()
    assert order2.stage_id == stage_templates[0].id
