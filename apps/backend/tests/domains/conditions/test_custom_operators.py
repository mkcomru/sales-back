"""Tests for custom operators ($stage_completed, $prev_stage_completed, $any)."""

from src.backend.core.conditions import evaluate_condition


class TestStageCompletedOperator:
    """Tests for $stage_completed operator."""

    def test_stage_completed_with_int(self):
        """Test $stage_completed with int stage_id."""
        condition = {"$stage_completed": 123}
        context = {
            "order_fields": {},
            "customer_fields": {},
            "completed_stages": [123, 456],
        }
        assert evaluate_condition(condition, context) is True

    def test_stage_completed_with_string(self):
        """Test $stage_completed with string stage_id."""
        condition = {"$stage_completed": "123"}
        context = {
            "order_fields": {},
            "customer_fields": {},
            "completed_stages": [123, 456],
        }
        assert evaluate_condition(condition, context) is True

    def test_stage_completed_not_completed(self):
        """Test $stage_completed with non-completed stage."""
        condition = {"$stage_completed": 789}
        context = {
            "order_fields": {},
            "customer_fields": {},
            "completed_stages": [123, 456],
        }
        assert evaluate_condition(condition, context) is False

    def test_stage_completed_empty_list(self):
        """Test $stage_completed with empty completed_stages."""
        condition = {"$stage_completed": 123}
        context = {
            "order_fields": {},
            "customer_fields": {},
            "completed_stages": [],
        }
        assert evaluate_condition(condition, context) is False

    def test_stage_completed_missing_context(self):
        """Test $stage_completed with missing completed_stages in context."""
        condition = {"$stage_completed": 123}
        context = {
            "order_fields": {},
            "customer_fields": {},
        }
        assert evaluate_condition(condition, context) is False

    def test_stage_completed_in_and(self):
        """Test $stage_completed in $and condition."""
        condition = {
            "$and": [
                {"order_fields.budget": {"$gte": 1000}},
                {"$stage_completed": 123},
            ]
        }
        context = {
            "order_fields": {"budget": 1500},
            "customer_fields": {},
            "completed_stages": [123],
        }
        assert evaluate_condition(condition, context) is True

    def test_stage_completed_in_or(self):
        """Test $stage_completed in $or condition."""
        condition = {
            "$or": [
                {"order_fields.budget": {"$gte": 10000}},
                {"$stage_completed": 123},
            ]
        }
        context = {
            "order_fields": {"budget": 500},
            "customer_fields": {},
            "completed_stages": [123],
        }
        assert evaluate_condition(condition, context) is True


class TestPrevStageCompletedOperator:
    """Tests for $prev_stage_completed operator."""

    def test_prev_stage_completed_true(self):
        """Test $prev_stage_completed when previous stage was completed."""
        condition = {"$prev_stage_completed": True}
        context = {
            "order_fields": {},
            "customer_fields": {},
            "completed_stages_by_position": {0: 123, 1: 456},
        }
        result = evaluate_condition(condition, context, current_stage_position=2)
        assert result is True

    def test_prev_stage_completed_false(self):
        """Test $prev_stage_completed when previous stage was not completed."""
        condition = {"$prev_stage_completed": True}
        context = {
            "order_fields": {},
            "customer_fields": {},
            "completed_stages_by_position": {0: 123},
        }
        result = evaluate_condition(condition, context, current_stage_position=2)
        assert result is False

    def test_prev_stage_completed_position_zero(self):
        """Test $prev_stage_completed with position 0 (no previous stage)."""
        condition = {"$prev_stage_completed": True}
        context = {
            "order_fields": {},
            "customer_fields": {},
            "completed_stages_by_position": {},
        }
        result = evaluate_condition(condition, context, current_stage_position=0)
        assert result is False

    def test_prev_stage_completed_no_position(self):
        """Test $prev_stage_completed without current_stage_position."""
        condition = {"$prev_stage_completed": True}
        context = {
            "order_fields": {},
            "customer_fields": {},
            "completed_stages_by_position": {0: 123},
        }
        result = evaluate_condition(condition, context, current_stage_position=None)
        assert result is False

    def test_prev_stage_completed_missing_context(self):
        """Test $prev_stage_completed with missing completed_stages_by_position."""
        condition = {"$prev_stage_completed": True}
        context = {
            "order_fields": {},
            "customer_fields": {},
        }
        result = evaluate_condition(condition, context, current_stage_position=2)
        assert result is False

    def test_prev_stage_completed_in_and(self):
        """Test $prev_stage_completed in $and condition."""
        condition = {
            "$and": [
                {"order_fields.budget": {"$gte": 1000}},
                {"$prev_stage_completed": True},
            ]
        }
        context = {
            "order_fields": {"budget": 1500},
            "customer_fields": {},
            "completed_stages_by_position": {0: 123},
        }
        result = evaluate_condition(condition, context, current_stage_position=1)
        assert result is True


class TestAnyOperator:
    """Tests for $any operator."""

    def test_any_always_true(self):
        """Test $any operator always returns True."""
        condition = {"$any": True}
        context = {}
        assert evaluate_condition(condition, context) is True

    def test_any_with_empty_context(self):
        """Test $any with empty context."""
        condition = {"$any": True}
        context = {"order_fields": {}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is True

    def test_any_in_and(self):
        """Test $any in $and condition."""
        condition = {
            "$and": [
                {"$any": True},
                {"order_fields.budget": {"$gte": 1000}},
            ]
        }
        context = {"order_fields": {"budget": 1500}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is True

    def test_any_in_or(self):
        """Test $any in $or condition."""
        condition = {
            "$or": [
                {"order_fields.budget": {"$gte": 10000}},
                {"$any": True},
            ]
        }
        context = {"order_fields": {"budget": 500}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is True


class TestCustomOperatorsCombined:
    """Tests combining custom operators with basic operators."""

    def test_stage_completed_and_field_condition(self):
        """Test $stage_completed combined with field condition."""
        condition = {
            "$and": [
                {"$stage_completed": 123},
                {"order_fields.budget": {"$gte": 1000}},
            ]
        }
        context = {
            "order_fields": {"budget": 1500},
            "customer_fields": {},
            "completed_stages": [123],
        }
        assert evaluate_condition(condition, context) is True

    def test_prev_stage_and_stage_completed(self):
        """Test $prev_stage_completed combined with $stage_completed."""
        condition = {
            "$and": [
                {"$prev_stage_completed": True},
                {"$stage_completed": 123},
            ]
        }
        context = {
            "order_fields": {},
            "customer_fields": {},
            "completed_stages": [123],
            "completed_stages_by_position": {0: 123},
        }
        result = evaluate_condition(condition, context, current_stage_position=1)
        assert result is True

    def test_any_as_fallback(self):
        """Test $any as fallback condition for initial stage."""
        condition = {
            "$or": [
                {"order_fields.budget": {"$gte": 1000}},
                {"$any": True},
            ]
        }
        context = {"order_fields": {"budget": 500}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is True
