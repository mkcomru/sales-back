"""Tests for basic MongoDB-like operators."""

from src.backend.core.conditions import evaluate_condition


class TestEqOperator:
    """Tests for $eq operator."""

    def test_eq_matches(self):
        """Test $eq operator with matching values."""
        condition = {"order_fields.budget": {"$eq": 1000}}
        context = {"order_fields": {"budget": 1000}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is True

    def test_eq_not_matches(self):
        """Test $eq operator with non-matching values."""
        condition = {"order_fields.budget": {"$eq": 1000}}
        context = {"order_fields": {"budget": 500}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is False

    def test_eq_implicit(self):
        """Test implicit equality (field: value without operator)."""
        condition = {"order_fields.budget": 1000}
        context = {"order_fields": {"budget": 1000}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is True

    def test_eq_none_value(self):
        """Test $eq with None value."""
        condition = {"order_fields.budget": {"$eq": None}}
        context = {"order_fields": {"budget": None}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is True

    def test_eq_missing_field(self):
        """Test $eq with missing field."""
        condition = {"order_fields.budget": {"$eq": 1000}}
        context = {"order_fields": {}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is False


class TestNeOperator:
    """Tests for $ne operator."""

    def test_ne_matches(self):
        """Test $ne operator with different values."""
        condition = {"order_fields.budget": {"$ne": 1000}}
        context = {"order_fields": {"budget": 500}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is True

    def test_ne_not_matches(self):
        """Test $ne operator with same values."""
        condition = {"order_fields.budget": {"$ne": 1000}}
        context = {"order_fields": {"budget": 1000}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is False


class TestComparisonOperators:
    """Tests for comparison operators ($gt, $gte, $lt, $lte)."""

    def test_gt_matches(self):
        """Test $gt operator."""
        condition = {"order_fields.budget": {"$gt": 1000}}
        context = {"order_fields": {"budget": 1500}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is True

    def test_gt_not_matches(self):
        """Test $gt operator with smaller value."""
        condition = {"order_fields.budget": {"$gt": 1000}}
        context = {"order_fields": {"budget": 500}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is False

    def test_gt_equal_value(self):
        """Test $gt operator with equal value."""
        condition = {"order_fields.budget": {"$gt": 1000}}
        context = {"order_fields": {"budget": 1000}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is False

    def test_gte_matches_greater(self):
        """Test $gte operator with greater value."""
        condition = {"order_fields.budget": {"$gte": 1000}}
        context = {"order_fields": {"budget": 1500}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is True

    def test_gte_matches_equal(self):
        """Test $gte operator with equal value."""
        condition = {"order_fields.budget": {"$gte": 1000}}
        context = {"order_fields": {"budget": 1000}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is True

    def test_gte_not_matches(self):
        """Test $gte operator with smaller value."""
        condition = {"order_fields.budget": {"$gte": 1000}}
        context = {"order_fields": {"budget": 500}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is False

    def test_lt_matches(self):
        """Test $lt operator."""
        condition = {"order_fields.budget": {"$lt": 1000}}
        context = {"order_fields": {"budget": 500}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is True

    def test_lt_not_matches(self):
        """Test $lt operator with greater value."""
        condition = {"order_fields.budget": {"$lt": 1000}}
        context = {"order_fields": {"budget": 1500}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is False

    def test_lte_matches_less(self):
        """Test $lte operator with smaller value."""
        condition = {"order_fields.budget": {"$lte": 1000}}
        context = {"order_fields": {"budget": 500}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is True

    def test_lte_matches_equal(self):
        """Test $lte operator with equal value."""
        condition = {"order_fields.budget": {"$lte": 1000}}
        context = {"order_fields": {"budget": 1000}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is True

    def test_comparison_with_none(self):
        """Test comparison operators with None value."""
        condition = {"order_fields.budget": {"$gt": 1000}}
        context = {"order_fields": {"budget": None}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is False

    def test_comparison_with_string_number(self):
        """Test comparison operators with numeric values (strict type checking)."""
        condition = {"order_fields.budget": {"$gte": 1000}}
        context = {"order_fields": {"budget": 1500}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is True


class TestExistsOperator:
    """Tests for $exists operator."""

    def test_exists_true(self):
        """Test $exists: true with existing field."""
        condition = {"customer_fields.city": {"$exists": True}}
        context = {"order_fields": {}, "customer_fields": {"city": "Moscow"}}
        assert evaluate_condition(condition, context) is True

    def test_exists_false(self):
        """Test $exists: false with missing field."""
        condition = {"customer_fields.city": {"$exists": False}}
        context = {"order_fields": {}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is True

    def test_exists_false_with_field(self):
        """Test $exists: false with existing field."""
        condition = {"customer_fields.city": {"$exists": False}}
        context = {"order_fields": {}, "customer_fields": {"city": "Moscow"}}
        assert evaluate_condition(condition, context) is False

    def test_exists_true_with_missing_field(self):
        """Test $exists: true with missing field."""
        condition = {"customer_fields.city": {"$exists": True}}
        context = {"order_fields": {}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is False

    def test_exists_with_none_value(self):
        """Test $exists treats null as not exists (field must have non-null value)."""
        condition = {"customer_fields.city": {"$exists": True}}
        context = {"order_fields": {}, "customer_fields": {"city": None}}
        assert evaluate_condition(condition, context) is False

    def test_exists_false_with_none_value(self):
        """Test $exists: false when value is null - null counts as not exists."""
        condition = {"customer_fields.city": {"$exists": False}}
        context = {"order_fields": {}, "customer_fields": {"city": None}}
        assert evaluate_condition(condition, context) is True


class TestAndOperator:
    """Tests for $and operator."""

    def test_and_all_true(self):
        """Test $and with all conditions true."""
        condition = {
            "$and": [
                {"order_fields.budget": {"$gte": 1000}},
                {"customer_fields.city": {"$exists": True}},
            ]
        }
        context = {"order_fields": {"budget": 1500}, "customer_fields": {"city": "Moscow"}}
        assert evaluate_condition(condition, context) is True

    def test_and_one_false(self):
        """Test $and with one condition false."""
        condition = {
            "$and": [
                {"order_fields.budget": {"$gte": 1000}},
                {"customer_fields.city": {"$exists": True}},
            ]
        }
        context = {"order_fields": {"budget": 500}, "customer_fields": {"city": "Moscow"}}
        assert evaluate_condition(condition, context) is False

    def test_and_empty_list(self):
        """Test $and with empty list."""
        condition = {"$and": []}
        context = {"order_fields": {}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is True

    def test_and_nested(self):
        """Test nested $and operators."""
        condition = {
            "$and": [
                {"order_fields.budget": {"$gte": 1000}},
                {
                    "$and": [
                        {"customer_fields.city": {"$exists": True}},
                        {"order_fields.dates": {"$exists": True}},
                    ]
                },
            ]
        }
        context = {
            "order_fields": {"budget": 1500, "dates": "2024-01-01"},
            "customer_fields": {"city": "Moscow"},
        }
        assert evaluate_condition(condition, context) is True


class TestOrOperator:
    """Tests for $or operator."""

    def test_or_one_true(self):
        """Test $or with one condition true."""
        condition = {
            "$or": [
                {"order_fields.budget": {"$gte": 1000}},
                {"customer_fields.city": {"$exists": True}},
            ]
        }
        context = {"order_fields": {"budget": 500}, "customer_fields": {"city": "Moscow"}}
        assert evaluate_condition(condition, context) is True

    def test_or_all_false(self):
        """Test $or with all conditions false."""
        condition = {
            "$or": [
                {"order_fields.budget": {"$gte": 1000}},
                {"customer_fields.city": {"$exists": True}},
            ]
        }
        context = {"order_fields": {"budget": 500}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is False

    def test_or_empty_list(self):
        """Test $or with empty list."""
        condition = {"$or": []}
        context = {"order_fields": {}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is False

    def test_or_nested(self):
        """Test nested $or operators."""
        condition = {
            "$or": [
                {"order_fields.budget": {"$gte": 1000}},
                {
                    "$or": [
                        {"customer_fields.city": {"$exists": True}},
                        {"order_fields.dates": {"$exists": True}},
                    ]
                },
            ]
        }
        context = {"order_fields": {"budget": 500}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is False


class TestNotOperator:
    """Tests for $not operator."""

    def test_not_true(self):
        """Test $not with true condition."""
        condition = {"$not": {"order_fields.budget": {"$gte": 1000}}}
        context = {"order_fields": {"budget": 500}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is True

    def test_not_false(self):
        """Test $not with false condition."""
        condition = {"$not": {"order_fields.budget": {"$gte": 1000}}}
        context = {"order_fields": {"budget": 1500}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is False

    def test_not_nested(self):
        """Test nested $not operators."""
        condition = {"$not": {"$not": {"order_fields.budget": {"$gte": 1000}}}}
        context = {"order_fields": {"budget": 1500}, "customer_fields": {}}
        assert evaluate_condition(condition, context) is True


class TestComplexConditions:
    """Tests for complex nested conditions."""

    def test_and_or_combination(self):
        """Test combination of $and and $or."""
        condition = {
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
        context = {
            "order_fields": {"budget": 1500},
            "customer_fields": {},
        }
        assert evaluate_condition(condition, context) is False

        context = {
            "order_fields": {"budget": 1500, "dates": "2024-01-01"},
            "customer_fields": {},
        }
        assert evaluate_condition(condition, context) is True

    def test_multiple_field_conditions(self):
        """Test multiple field conditions."""
        condition = {
            "order_fields.budget": {"$gte": 1000},
            "customer_fields.city": {"$exists": True},
        }
        context = {
            "order_fields": {"budget": 1500},
            "customer_fields": {"city": "Moscow"},
        }
        assert evaluate_condition(condition, context) is True
