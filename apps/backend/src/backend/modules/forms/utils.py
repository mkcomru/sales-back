"""Utility functions for form API key generation."""

import hashlib
import secrets


def generate_form_api_key() -> tuple[str, str]:
    """Generate form API key. Returns (raw_key, key_hash)."""
    raw_key = f"form_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    return raw_key, key_hash


def hash_form_api_key(raw_key: str) -> str:
    """Hash API key for lookup."""
    return hashlib.sha256(raw_key.encode()).hexdigest()
