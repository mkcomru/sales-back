"""Task-related exceptions."""

from fastapi import HTTPException, status


class TaskNotFoundError(HTTPException):
    """Raised when task is not found."""

    def __init__(self, task_id: int):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task {task_id} not found")


class OrderNotFoundError(HTTPException):
    """Raised when order is not found."""

    def __init__(self, order_id: int):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=f"Order {order_id} not found")
