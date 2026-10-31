"""Structured outputs parsing and validation helpers.

This module provides utilities for parsing structured outputs from LLM responses,
with support for native OpenAI structured outputs and fallback validation
for other providers.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from pydantic import BaseModel, ValidationError

log = structlog.get_logger()

MAX_RETRIES = 3


def parse_openai_response[T: BaseModel](
    response: Any,
    response_model: type[T],
) -> T:
    """Parse native OpenAI structured output response.

    Args:
        response: OpenAI response object with parsed attribute
        response_model: Pydantic model class for structured output

    Returns:
        Parsed and validated instance of response_model

    Raises:
        ValueError: If parsed content is missing or validation fails
    """
    parsed = response.choices[0].message.parsed
    if parsed is None:
        raise ValueError("No parsed content in OpenAI response")

    if not isinstance(parsed, response_model):
        try:
            return response_model.model_validate(parsed)
        except ValidationError as e:
            raise ValueError(f"Validation failed: {e}") from e

    return parsed


def parse_fallback[T: BaseModel](
    content: str,
    response_model: type[T],
    *,
    retries: int = MAX_RETRIES,
) -> T:
    """Parse and validate structured output from text content (fallback).

    Attempts to extract JSON from content and validate against response_model.
    Supports retries with improved instructions if validation fails.

    Args:
        content: Text content containing JSON (may have markdown code blocks)
        response_model: Pydantic model class for structured output
        retries: Maximum number of retry attempts (default: MAX_RETRIES)

    Returns:
        Parsed and validated instance of response_model

    Raises:
        ValueError: If JSON extraction or validation fails after retries
    """
    if not content:
        raise ValueError("Empty content for fallback parsing")

    content_cleaned = _extract_json_from_text(content)

    for attempt in range(retries):
        try:
            raw_json = json.loads(content_cleaned)
            return response_model.model_validate(raw_json)
        except json.JSONDecodeError as e:
            if attempt < retries - 1:
                log.warning(
                    "struct.parse_fallback.json_error",
                    attempt=attempt + 1,
                    error=str(e),
                    retrying=True,
                )
                content_cleaned = _extract_json_from_text(content_cleaned)
                continue
            raise ValueError(f"Invalid JSON in response after {retries} attempts: {e}") from e
        except ValidationError as e:
            if attempt < retries - 1:
                log.warning(
                    "struct.parse_fallback.validation_error",
                    attempt=attempt + 1,
                    error=str(e),
                    retrying=True,
                )
                schema = response_model.model_json_schema()
                content_cleaned = _try_fix_json_with_schema(content_cleaned, schema)
                continue
            raise ValueError(f"Validation failed after {retries} attempts: {e}") from e

    raise ValueError(f"Failed to parse after {retries} attempts")


def _extract_json_from_text(text: str) -> str:
    """Extract JSON from text, handling markdown code blocks.

    Args:
        text: Text that may contain JSON in markdown code blocks or plain

    Returns:
        Extracted JSON string
    """
    text = text.strip()

    if text.startswith("```"):
        lines = text.split("\n")
        if len(lines) > 1:
            first_line = lines[0]
            if "json" in first_line.lower():
                text = "\n".join(lines[1:])
            else:
                text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3].strip()

    if text.startswith("```"):
        text = text[3:].strip()
    if text.endswith("```"):
        text = text[:-3].strip()

    return text.strip()


def _try_fix_json_with_schema(content: str, schema: dict[str, Any]) -> str:
    """Attempt to fix JSON content using schema hints.

    Args:
        content: JSON string that failed validation
        schema: JSON schema for the expected structure

    Returns:
        Potentially fixed JSON string
    """
    try:
        parsed = json.loads(content)
        required_fields = schema.get("required", [])
        properties = schema.get("properties", {})

        for field in required_fields:
            if field not in parsed:
                field_schema = properties.get(field, {})
                default_type = field_schema.get("type")
                if default_type == "string":
                    parsed[field] = ""
                elif default_type == "array":
                    parsed[field] = []
                elif default_type == "object":
                    parsed[field] = {}
                elif default_type == "boolean":
                    parsed[field] = False
                elif default_type in ("number", "integer"):
                    parsed[field] = 0

        return json.dumps(parsed, ensure_ascii=False)
    except Exception:
        return content
