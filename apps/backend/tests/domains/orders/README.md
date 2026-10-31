# Orders Domain Tests

Tests for the Orders module and Order Logs functionality.

## Test Files

### `test_order_logs.py`
Tests for Order activity logging:
- Order creation logging
- Stage change logging
- Assignee change logging
- Field change logging
- Order close logging
- Comment creation
- System vs manual action differentiation

### `test_routers.py`
API endpoint tests:
- Order CRUD operations
- Order logs retrieval
- Comment creation
- Internal (service) vs public endpoints
- Authentication and authorization

## Running Tests

Run all orders tests:
```bash
uv run pytest tests/domains/orders/
```

Run specific test file:
```bash
uv run pytest tests/domains/orders/test_order_logs.py
```

Run specific test:
```bash
uv run pytest tests/domains/orders/test_order_logs.py::test_create_order_creates_log
```

## Fixtures

Available in `conftest.py`:
- `orders_repo` - OrdersRepository instance
- `order_service` - OrderService instance
- `customer_with_company` - Customer with Company
- `order_with_customer` - Order with Customer and Company
- `manager_user` - CompanyUser with manager role

