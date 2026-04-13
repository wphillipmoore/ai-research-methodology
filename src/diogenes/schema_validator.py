"""JSON Schema validation for research input and sub-agent output."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

# Schemas are packaged with the module
_SCHEMAS_DIR = Path(__file__).parent / "schemas"


class ValidationError(Exception):
    """Raised when JSON validation fails."""

    def __init__(self, schema_name: str, message: str, path: str = "") -> None:
        """Initialize with the schema name, error message, and JSON path."""
        self.schema_name = schema_name
        self.path = path
        detail = f" at '{path}'" if path else ""
        super().__init__(f"Validation failed ({schema_name}){detail}: {message}")


def _load_schema(schema_name: str) -> dict[str, Any]:
    """Load a JSON schema file by name.

    Args:
        schema_name: Schema filename (e.g., 'research-input.schema.json').

    Returns:
        Parsed schema dict.

    Raises:
        ValidationError: If the schema file doesn't exist or is invalid JSON.

    """
    schema_path = _SCHEMAS_DIR / schema_name
    if not schema_path.exists():
        msg = f"Schema file not found: {schema_path}"
        raise ValidationError(schema_name, msg)

    try:
        return json.loads(schema_path.read_text())  # type: ignore[no-any-return]
    except json.JSONDecodeError as e:
        msg = f"Invalid JSON in schema file: {e}"
        raise ValidationError(schema_name, msg) from e


def validate_research_input(data: dict[str, Any]) -> dict[str, Any]:
    """Validate a research input dict against the research-input schema.

    Args:
        data: The input data to validate.

    Returns:
        The validated data (unchanged if valid).

    Raises:
        ValidationError: If validation fails.

    """
    return validate(data, "research-input.schema.json")


def validate(data: dict[str, Any], schema_name: str) -> dict[str, Any]:
    """Validate data against a named schema.

    Args:
        data: The data to validate.
        schema_name: Schema filename in the schemas directory.

    Returns:
        The validated data (unchanged if valid).

    Raises:
        ValidationError: If validation fails.

    """
    schema = _load_schema(schema_name)

    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as e:
        path = ".".join(str(p) for p in e.absolute_path)
        raise ValidationError(schema_name, e.message, path) from e

    return data


def is_json(text: str) -> bool:
    """Check if a string is valid JSON.

    Args:
        text: The string to check.

    Returns:
        True if the string is valid JSON, False otherwise.

    """
    try:
        json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return False
    return True


def parse_input_file(file_path: str | Path) -> dict[str, Any] | str:
    """Read an input file and return JSON dict or raw text.

    If the file contains valid JSON, parse and return as a dict.
    Otherwise, return the raw text content for AI parsing.

    Args:
        file_path: Path to the input file.

    Returns:
        Parsed JSON dict if the file is valid JSON, otherwise raw text string.

    Raises:
        FileNotFoundError: If the file doesn't exist.

    """
    path = Path(file_path)
    if not path.exists():
        msg = f"Input file not found: {path}"
        raise FileNotFoundError(msg)

    content = path.read_text().strip()

    if is_json(content):
        return json.loads(content)  # type: ignore[no-any-return]

    return content
