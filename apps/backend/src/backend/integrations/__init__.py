"""Provider packages for external integrations.

Each provider lives in its own subdirectory and registers service overrides
at import time via register_override(). Import provider packages here
to trigger registration.
"""

from src.backend.integrations import yclients  # noqa: F401
