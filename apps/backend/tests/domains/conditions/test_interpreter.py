"""Tests for condition interpreter (evaluation edge cases)."""

import pytest

from src.backend.core.conditions import (
    ConditionEvaluationError,
    evaluate_condition,
    evaluate_condition_detailed,
)


class TestNoneAndEmptyConditions:
    """Tests for None and empty conditions."""

    def test_none_condition(self):
        """Test None condition returns False."""
        context = {"order_fields": {}, "customer_fields": {}}
        assert evaluate_condition(None, context) is False

    def test_empty_dict_condition(self):
        """Test empty dict condition returns True."""
        context = {"order_fields": {}, "customer_fields": {}}
        assert evaluate_condition({}, context) is True

    def test_non_dict_condition(self):
        """Test non-dict condition raises error."""
        with pytest.raises(ConditionEvaluationError):
            evaluate_condition("not a dict", {})


class TestContextNormalization:
    """Tests for context normalization."""

    def test_order_fields_normalization(self):
        """Test order_fields are normalized to dot notation."""
        condition = {"order_fields.budget": {"$gte": 1000}}
        context = {"order_fields": {"budget": 1500}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is True

    def test_customer_fields_normalization(self):
        """Test customer_fields are normalized to dot notation."""
        condition = {"customer_fields.city": {"$exists": True}}
        context = {"order_fields": {}, "customer_fields": {"city": "Moscow"}}
        assert evaluate_condition(condition, context) is True

    def test_both_fields_normalized(self):
        """Test both order_fields and customer_fields normalized."""
        condition = {
            "$and": [
                {"order_fields.budget": {"$gte": 1000}},
                {"customer_fields.city": {"$exists": True}},
            ]
        }
        context = {
            "order_fields": {"budget": 1500},
            "customer_fields": {"city": "Moscow"},
        }
        assert evaluate_condition(condition, context) is True

    def test_missing_order_fields(self):
        """Test missing order_fields in context."""
        condition = {"order_fields.budget": {"$gte": 1000}}
        context = {"customer_fields": {}}
        assert evaluate_condition(condition, context) is False

    def test_missing_customer_fields(self):
        """Test missing customer_fields in context."""
        condition = {"customer_fields.city": {"$exists": True}}
        context = {"order_fields": {}}
        assert evaluate_condition(condition, context) is False


class TestFieldPathResolution:
    """Tests for field path resolution."""

    def test_simple_field_path(self):
        """Test simple field path without dot."""
        condition = {"test_field": {"$eq": "value"}}
        context = {"test_field": "value", "order_fields": {}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is True

    def test_dot_notation_field_path(self):
        """Test dot notation field path."""
        condition = {"order_fields.budget": {"$gte": 1000}}
        context = {"order_fields": {"budget": 1500}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is True

    def test_missing_field_in_path(self):
        """Test missing field in dot notation path."""
        condition = {"order_fields.budget": {"$gte": 1000}}
        context = {"order_fields": {}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is False

    def test_none_value_in_field(self):
        """Test None value in field."""
        condition = {"order_fields.budget": {"$eq": None}}
        context = {"order_fields": {"budget": None}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is True


class TestComplexNestedConditions:
    """Tests for complex nested conditions."""

    def test_triple_nested_and(self):
        """Test triple nested $and."""
        condition = {
            "$and": [
                {
                    "$and": [
                        {"order_fields.budget": {"$gte": 1000}},
                        {
                            "$and": [
                                {"customer_fields.city": {"$exists": True}},
                            ]
                        },
                    ]
                },
            ]
        }
        context = {
            "order_fields": {"budget": 1500},
            "customer_fields": {"city": "Moscow"},
        }
        assert evaluate_condition(condition, context) is True

    def test_and_or_not_combination(self):
        """Test combination of $and, $or, and $not."""
        condition = {
            "$and": [
                {"order_fields.budget": {"$gte": 1000}},
                {
                    "$or": [
                        {"customer_fields.city": {"$exists": True}},
                        {"$not": {"order_fields.dates": {"$exists": False}}},
                    ]
                },
            ]
        }
        context = {
            "order_fields": {"budget": 1500, "dates": "2024-01-01"},
            "customer_fields": {},
        }
        assert evaluate_condition(condition, context) is True

    def test_multiple_operators_same_level(self):
        """Test multiple operators using proper nested structure."""
        # AICODE-NOTE: Cannot mix $and and $or at same level - must use nested structure
        condition = {
            "$and": [
                {"order_fields.budget": {"$gte": 1000}},
                {"order_fields.dates": {"$exists": True}},
                {
                    "$or": [
                        {"customer_fields.city": {"$exists": True}},
                    ]
                },
            ],
        }
        context = {
            "order_fields": {"budget": 1500, "dates": "2024-01-01"},
            "customer_fields": {},
        }
        # Should be False because city doesn't exist, but budget and dates conditions are met
        # However, $or inside $and requires city to exist, so overall result is False
        assert evaluate_condition(condition, context) is False

        # Test with city present - should be True
        context_with_city = {
            "order_fields": {"budget": 1500, "dates": "2024-01-01"},
            "customer_fields": {"city": "Moscow"},
        }
        assert evaluate_condition(condition, context_with_city) is True


class TestErrorHandling:
    """Tests for error handling."""

    def test_missing_context_prefix(self):
        """Test missing context prefix returns False (field not found)."""
        condition = {"order_fields.budget": {"$gte": 1000}}
        context = {"customer_fields": {}}
        assert evaluate_condition(condition, context) is False

    def test_invalid_field_path_format(self):
        """Test invalid field path format."""
        condition = {"order_fields.budget.extra": {"$gte": 1000}}
        context = {"order_fields": {"budget": 1500}, "customer_fields": {}}
        with pytest.raises(ConditionEvaluationError):
            evaluate_condition(condition, context)

    def test_and_with_non_list(self):
        """Test $and with non-list raises error."""
        condition = {"$and": "not a list"}
        context = {"order_fields": {}, "customer_fields": {}}
        with pytest.raises(ConditionEvaluationError):
            evaluate_condition(condition, context)

    def test_or_with_non_list(self):
        """Test $or with non-list raises error."""
        condition = {"$or": "not a list"}
        context = {"order_fields": {}, "customer_fields": {}}
        with pytest.raises(ConditionEvaluationError):
            evaluate_condition(condition, context)

    def test_unknown_operator(self):
        """Test unknown operator raises error."""
        condition = {"$unknown": 123}
        context = {"order_fields": {}, "customer_fields": {}}
        with pytest.raises(ConditionEvaluationError):
            evaluate_condition(condition, context)


class TestRealWorldScenarios:
    """Tests for real-world usage scenarios."""

    def test_initial_stage_condition(self):
        """Test condition for initial stage (accepts all orders)."""
        condition = {"$any": True}
        context = {"order_fields": {}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is True

    def test_budget_threshold_condition(self):
        """Test budget threshold condition."""
        condition = {"order_fields.budget": {"$gte": 1000}}
        context = {"order_fields": {"budget": 1500}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is True

        context = {"order_fields": {"budget": 500}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is False

    def test_customer_info_required(self):
        """Test condition requiring customer information."""
        condition = {
            "$and": [
                {"customer_fields.city": {"$exists": True}},
                {"customer_fields.email": {"$exists": True}},
            ]
        }
        context = {
            "order_fields": {},
            "customer_fields": {"city": "Moscow", "email": "test@example.com"},
        }
        assert evaluate_condition(condition, context) is True

        context = {
            "order_fields": {},
            "customer_fields": {"city": "Moscow"},
        }
        assert evaluate_condition(condition, context) is False

    def test_stage_progression_condition(self):
        """Test condition checking stage progression."""
        condition = {
            "$and": [
                {"$prev_stage_completed": True},
                {"order_fields.budget": {"$gte": 1000}},
            ]
        }
        context = {
            "order_fields": {"budget": 1500},
            "customer_fields": {},
            "completed_stages_by_position": {0: 123},
        }
        result = evaluate_condition(condition, context, current_stage_position=1)
        assert result is True

    def test_complex_funnel_condition(self):
        """Test complex funnel condition."""
        condition = {
            "$and": [
                {"$stage_completed": 123},
                {"order_fields.budget": {"$gte": 1000}},
                {
                    "$or": [
                        {"customer_fields.city": {"$exists": True}},
                        {"order_fields.dates": {"$exists": True}},
                    ]
                },
            ]
        }
        context = {
            "order_fields": {"budget": 1500, "dates": "2024-01-01"},
            "customer_fields": {},
            "completed_stages": [123],
        }
        assert evaluate_condition(condition, context) is True


# ---------------------------------------------------------------------------
# Tests for evaluate_condition_detailed
# ---------------------------------------------------------------------------


class TestDetailedNoneAndEmpty:
    def test_none_returns_false_report(self):
        ctx = {"order_fields": {}, "customer_fields": {}}
        report = evaluate_condition_detailed(None, ctx)
        assert report.overall is False
        assert report.root.logic == "and"
        assert report.root.children == []

    def test_empty_dict_returns_true_report(self):
        ctx = {"order_fields": {}, "customer_fields": {}}
        report = evaluate_condition_detailed({}, ctx)
        assert report.overall is True

    def test_non_dict_raises(self):
        with pytest.raises(ConditionEvaluationError):
            evaluate_condition_detailed("bad", {})


class TestDetailedFieldConditions:
    def test_simple_eq_pass(self):
        condition = {"order_fields.budget": 1000}
        ctx = {"order_fields": {"budget": 1000}, "customer_fields": {}}
        report = evaluate_condition_detailed(condition, ctx)
        assert report.overall is True
        clause = report.root.children[0]
        assert clause.type == "clause"
        assert clause.operator == "$eq"
        assert clause.actual == 1000
        assert clause.result is True

    def test_simple_eq_fail(self):
        condition = {"order_fields.budget": 1000}
        ctx = {"order_fields": {"budget": 500}, "customer_fields": {}}
        report = evaluate_condition_detailed(condition, ctx)
        assert report.overall is False
        clause = report.root.children[0]
        assert clause.result is False
        assert clause.actual == 500

    def test_gte_with_actual(self):
        condition = {"order_fields.budget": {"$gte": 1000}}
        ctx = {"order_fields": {"budget": 1500}, "customer_fields": {}}
        report = evaluate_condition_detailed(condition, ctx)
        assert report.overall is True
        clause = report.root.children[0]
        assert clause.operator == "$gte"
        assert clause.expected == 1000
        assert clause.actual == 1500

    def test_missing_field_actual_is_none(self):
        condition = {"order_fields.budget": {"$gte": 1000}}
        ctx = {"order_fields": {}, "customer_fields": {}}
        report = evaluate_condition_detailed(condition, ctx)
        assert report.overall is False
        clause = report.root.children[0]
        assert clause.actual is None
        assert clause.result is False

    def test_exists_true(self):
        condition = {"customer_fields.city": {"$exists": True}}
        ctx = {"order_fields": {}, "customer_fields": {"city": "Moscow"}}
        report = evaluate_condition_detailed(condition, ctx)
        clause = report.root.children[0]
        assert clause.operator == "$exists"
        assert "exists" in clause.description
        assert clause.result is True

    def test_multiple_operators_same_field(self):
        condition = {"order_fields.budget": {"$gte": 100, "$lte": 5000}}
        ctx = {"order_fields": {"budget": 1000}, "customer_fields": {}}
        report = evaluate_condition_detailed(condition, ctx)
        assert report.overall is True
        group = report.root.children[0]
        assert group.type == "group"
        assert group.logic == "and"
        assert len(group.children) == 2


class TestDetailedLogicalOperators:
    def test_and_group(self):
        condition = {
            "$and": [
                {"order_fields.budget": {"$gte": 1000}},
                {"customer_fields.city": {"$exists": True}},
            ]
        }
        ctx = {
            "order_fields": {"budget": 1500},
            "customer_fields": {"city": "Moscow"},
        }
        report = evaluate_condition_detailed(condition, ctx)
        assert report.overall is True
        and_group = report.root.children[0]
        assert and_group.type == "group"
        assert and_group.logic == "and"
        assert len(and_group.children) == 2

    def test_or_group_partial(self):
        condition = {
            "$or": [
                {"order_fields.budget": {"$gte": 10000}},
                {"customer_fields.city": {"$exists": True}},
            ]
        }
        ctx = {
            "order_fields": {"budget": 500},
            "customer_fields": {"city": "Moscow"},
        }
        report = evaluate_condition_detailed(condition, ctx)
        assert report.overall is True
        or_group = report.root.children[0]
        assert or_group.logic == "or"
        assert or_group.children[0].result is False
        assert or_group.children[1].result is True

    def test_not_group(self):
        condition = {"$not": {"order_fields.budget": {"$gte": 1000}}}
        ctx = {"order_fields": {"budget": 500}, "customer_fields": {}}
        report = evaluate_condition_detailed(condition, ctx)
        assert report.overall is True
        not_group = report.root.children[0]
        assert not_group.type == "group"
        assert not_group.logic == "not"
        assert not_group.result is True


class TestDetailedCustomOperators:
    def test_any(self):
        condition = {"$any": True}
        ctx = {"order_fields": {}, "customer_fields": {}}
        report = evaluate_condition_detailed(condition, ctx)
        assert report.overall is True
        clause = report.root.children[0]
        assert clause.operator == "$any"

    def test_stage_completed_true(self):
        condition = {"$stage_completed": 123}
        ctx = {"order_fields": {}, "customer_fields": {}, "completed_stages": [123]}
        report = evaluate_condition_detailed(condition, ctx)
        assert report.overall is True
        clause = report.root.children[0]
        assert clause.operator == "$stage_completed"
        assert clause.expected == 123

    def test_stage_completed_false(self):
        condition = {"$stage_completed": 123}
        ctx = {"order_fields": {}, "customer_fields": {}, "completed_stages": []}
        report = evaluate_condition_detailed(condition, ctx)
        assert report.overall is False

    def test_prev_stage_completed(self):
        condition = {"$prev_stage_completed": True}
        ctx = {
            "order_fields": {},
            "customer_fields": {},
            "completed_stages_by_position": {0: 10},
        }
        report = evaluate_condition_detailed(condition, ctx, current_stage_position=1)
        assert report.overall is True


class TestDetailedNestedGroups:
    def test_and_inside_or(self):
        condition = {
            "$or": [
                {
                    "$and": [
                        {"order_fields.budget": {"$gte": 1000}},
                        {"customer_fields.city": {"$exists": True}},
                    ]
                },
                {"$stage_completed": 5},
            ]
        }
        ctx = {
            "order_fields": {"budget": 1500},
            "customer_fields": {"city": "Moscow"},
            "completed_stages": [],
        }
        report = evaluate_condition_detailed(condition, ctx)
        assert report.overall is True
        or_group = report.root.children[0]
        assert or_group.logic == "or"
        and_child = or_group.children[0]
        assert and_child.type == "group"
        assert and_child.logic == "and"
        assert and_child.result is True

    def test_consistency_with_evaluate_condition(self):
        """Detailed report overall must match evaluate_condition bool."""
        conditions = [
            {"$any": True},
            {"order_fields.x": 1},
            {"order_fields.x": {"$gte": 5}},
            {"$and": [{"order_fields.x": 1}, {"order_fields.y": 2}]},
            {"$or": [{"order_fields.x": 99}, {"order_fields.y": 2}]},
            {"$not": {"order_fields.x": 99}},
            {"$stage_completed": 7},
        ]
        ctx = {
            "order_fields": {"x": 1, "y": 2},
            "customer_fields": {},
            "completed_stages": [7],
            "completed_stages_by_position": {0: 7},
        }
        for cond in conditions:
            bool_result = evaluate_condition(cond, ctx, current_stage_position=1)
            report = evaluate_condition_detailed(cond, ctx, current_stage_position=1)
            assert report.overall == bool_result, f"Mismatch for condition {cond}"
