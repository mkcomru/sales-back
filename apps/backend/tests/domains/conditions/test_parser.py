"""Tests for condition parser (syntax validation)."""

import pytest

from src.backend.core.conditions import ConditionSyntaxError, validate_condition


class TestValidConditions:
    """Tests for valid condition syntax."""

    def test_empty_dict(self):
        """Test empty dict is valid."""
        validate_condition({})

    def test_simple_field_condition(self):
        """Test simple field condition."""
        validate_condition({"order_fields.budget": 1000})

    def test_field_with_operator(self):
        """Test field with operator."""
        validate_condition({"order_fields.budget": {"$gte": 1000}})

    def test_and_operator(self):
        """Test $and operator."""
        validate_condition({"$and": [{"order_fields.budget": {"$gte": 1000}}]})

    def test_or_operator(self):
        """Test $or operator."""
        validate_condition({"$or": [{"order_fields.budget": {"$gte": 1000}}]})

    def test_not_operator(self):
        """Test $not operator."""
        validate_condition({"$not": {"order_fields.budget": {"$gte": 1000}}})

    def test_comparison_operators(self):
        """Test comparison operators."""
        validate_condition({"order_fields.budget": {"$gt": 1000}})
        validate_condition({"order_fields.budget": {"$gte": 1000}})
        validate_condition({"order_fields.budget": {"$lt": 1000}})
        validate_condition({"order_fields.budget": {"$lte": 1000}})

    def test_exists_operator(self):
        """Test $exists operator."""
        validate_condition({"customer_fields.city": {"$exists": True}})
        validate_condition({"customer_fields.city": {"$exists": False}})

    def test_custom_operators(self):
        """Test custom operators."""
        validate_condition({"$stage_completed": 123})
        validate_condition({"$stage_completed": "123"})
        validate_condition({"$prev_stage_completed": True})
        validate_condition({"$any": True})

    def test_nested_conditions(self):
        """Test nested conditions."""
        validate_condition(
            {
                "$and": [
                    {"order_fields.budget": {"$gte": 1000}},
                    {
                        "$or": [
                            {"customer_fields.city": {"$exists": True}},
                            {"order_fields.dates": {"$exists": True}},
                        ]
                    },
                ]
            }
        )

    def test_primitive_values(self):
        """Test primitive values are valid."""
        validate_condition(None)
        validate_condition("string")
        validate_condition(123)
        validate_condition(45.6)
        validate_condition(True)
        validate_condition(False)

    def test_list_conditions(self):
        """Test list conditions."""
        validate_condition([{"order_fields.budget": {"$gte": 1000}}])


class TestInvalidConditions:
    """Tests for invalid condition syntax."""

    def test_unknown_operator(self):
        """Test unknown operator raises error."""
        with pytest.raises(ConditionSyntaxError) as exc_info:
            validate_condition({"$unknown": 123})
        assert "Unknown operator" in str(exc_info.value)

    def test_and_not_list(self):
        """Test $and with non-list value."""
        with pytest.raises(ConditionSyntaxError) as exc_info:
            validate_condition({"$and": "not a list"})
        assert "$and requires a list" in str(exc_info.value)

    def test_or_not_list(self):
        """Test $or with non-list value."""
        with pytest.raises(ConditionSyntaxError) as exc_info:
            validate_condition({"$or": "not a list"})
        assert "$or requires a list" in str(exc_info.value)

    def test_stage_completed_invalid_type(self):
        """Test $stage_completed with invalid type."""
        with pytest.raises(ConditionSyntaxError) as exc_info:
            validate_condition({"$stage_completed": True})
        assert "$stage_completed requires int or string" in str(exc_info.value)

    def test_prev_stage_completed_invalid_value(self):
        """Test $prev_stage_completed with invalid value."""
        with pytest.raises(ConditionSyntaxError) as exc_info:
            validate_condition({"$prev_stage_completed": False})
        assert "$prev_stage_completed requires boolean true" in str(exc_info.value)

    def test_any_invalid_value(self):
        """Test $any with invalid value."""
        with pytest.raises(ConditionSyntaxError) as exc_info:
            validate_condition({"$any": False})
        assert "$any requires boolean true" in str(exc_info.value)

    def test_exists_invalid_type(self):
        """Test $exists with invalid type."""
        with pytest.raises(ConditionSyntaxError) as exc_info:
            validate_condition({"customer_fields.city": {"$exists": "yes"}})
        assert "$exists requires boolean value" in str(exc_info.value)

    def test_empty_operator_dict(self):
        """Test empty operator dict raises error."""
        with pytest.raises(ConditionSyntaxError) as exc_info:
            validate_condition({"order_fields.budget": {}})
        assert "Empty operator dict" in str(exc_info.value)

    def test_field_with_non_operator_key(self):
        """Test field condition with non-operator key."""
        with pytest.raises(ConditionSyntaxError) as exc_info:
            validate_condition({"order_fields.budget": {"invalid": 1000}})
        assert "Expected operator starting with $" in str(exc_info.value)

    def test_invalid_nested_condition(self):
        """Test invalid nested condition."""
        with pytest.raises(ConditionSyntaxError) as exc_info:
            validate_condition({"$and": [{"$unknown": 123}]})
        assert "Unknown operator" in str(exc_info.value)


class TestEdgeCases:
    """Tests for edge cases in validation."""

    def test_deeply_nested_conditions(self):
        """Test deeply nested conditions."""
        condition = {
            "$and": [
                {
                    "$or": [
                        {"$and": [{"order_fields.budget": {"$gte": 1000}}]},
                        {"customer_fields.city": {"$exists": True}},
                    ]
                },
                {"order_fields.dates": {"$exists": True}},
            ]
        }
        validate_condition(condition)

    def test_multiple_field_conditions(self):
        """Test multiple field conditions in one dict."""
        condition = {
            "order_fields.budget": {"$gte": 1000},
            "customer_fields.city": {"$exists": True},
            "order_fields.dates": {"$exists": True},
        }
        validate_condition(condition)

    def test_complex_condition(self):
        """Test complex real-world condition."""
        condition = {
            "$and": [
                {"order_fields.budget": {"$gte": 1000}},
                {"customer_fields.city": {"$exists": True}},
                {
                    "$or": [
                        {"order_fields.dates": {"$exists": True}},
                        {"$stage_completed": 123},
                    ]
                },
            ]
        }
        validate_condition(condition)

    def test_list_with_multiple_items(self):
        """Test list with multiple condition items."""
        validate_condition(
            [
                {"order_fields.budget": {"$gte": 1000}},
                {"customer_fields.city": {"$exists": True}},
            ]
        )

    def test_condition_with_none_value(self):
        """Test condition with None value."""
        validate_condition({"order_fields.budget": None})
        validate_condition({"order_fields.budget": {"$eq": None}})

    def test_condition_with_zero(self):
        """Test condition with zero value."""
        validate_condition({"order_fields.budget": 0})
        validate_condition({"order_fields.budget": {"$gte": 0}})

    def test_condition_with_empty_string(self):
        """Test condition with empty string."""
        validate_condition({"customer_fields.name": ""})
        validate_condition({"customer_fields.name": {"$eq": ""}})
