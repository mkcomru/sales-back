"""Exceptions for conditions engine."""


class ConditionSyntaxError(ValueError):
    """Raised when condition JSON has invalid syntax."""

    def __init__(self, message: str, path: str | None = None):
        super().__init__(message)
        self.path = path


class ConditionEvaluationError(RuntimeError):
    """Raised when condition evaluation fails (e.g., missing context data)."""

    def __init__(self, message: str, path: str | None = None):
        super().__init__(message)
        self.path = path
