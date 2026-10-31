"""Rate limiting configuration for forms module."""

from slowapi import Limiter
from slowapi.util import get_remote_address

# AICODE-NOTE: Using in-memory storage to avoid import-time settings validation.
# Memory storage is sufficient for rate limiting - it doesn't require persistence.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["60/minute"],
)
