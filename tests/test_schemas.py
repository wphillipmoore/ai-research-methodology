"""Tests for JSON schema validation."""

import json
from pathlib import Path

import jsonschema
import pytest

SCHEMAS_DIR = Path(__file__).parent.parent / "docs" / "design" / "schemas"


@pytest.fixture
def research_input_schema() -> dict:
    """Load the research input schema."""
    schema_path = SCHEMAS_DIR / "research-input.schema.json"
    with schema_path.open() as f:
        return json.load(f)


@pytest.fixture
def research_input_example() -> dict:
    """Load the research input example."""
    example_path = SCHEMAS_DIR / "research-input.example.json"
    with example_path.open() as f:
        return json.load(f)


class TestResearchInputSchema:
    """Tests for the research input JSON schema."""

    def test_example_validates(self, research_input_schema: dict, research_input_example: dict) -> None:
        """The example file should validate against the schema."""
        jsonschema.validate(instance=research_input_example, schema=research_input_schema)

    def test_empty_object_fails(self, research_input_schema: dict) -> None:
        """An empty object should fail — needs at least claims or queries."""
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance={}, schema=research_input_schema)

    def test_claims_only(self, research_input_schema: dict) -> None:
        """Claims without queries should be valid."""
        data = {"claims": [{"text": "Test claim"}]}
        jsonschema.validate(instance=data, schema=research_input_schema)

    def test_queries_only(self, research_input_schema: dict) -> None:
        """Queries without claims should be valid."""
        data = {"queries": [{"text": "Test query"}]}
        jsonschema.validate(instance=data, schema=research_input_schema)

    def test_axioms_only_fails(self, research_input_schema: dict) -> None:
        """Axioms alone should fail — need at least claims or queries."""
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance={"axioms": [{"text": "An axiom"}]}, schema=research_input_schema)

    def test_claim_with_candidate_evidence(self, research_input_schema: dict) -> None:
        """A claim with candidate evidence should validate."""
        data = {
            "claims": [
                {
                    "text": "Test claim",
                    "candidate_evidence": [
                        {
                            "url": "https://example.com/paper",
                            "description": "A relevant paper",
                        }
                    ],
                }
            ]
        }
        jsonschema.validate(instance=data, schema=research_input_schema)

    def test_claim_missing_text_fails(self, research_input_schema: dict) -> None:
        """A claim without text should fail."""
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance={"claims": [{}]}, schema=research_input_schema)

    def test_config_defaults(self, research_input_schema: dict) -> None:
        """Config with just output should validate."""
        data = {
            "claims": [{"text": "Test"}],
            "config": {"output": "/tmp/test", "runs": 1},
        }
        jsonschema.validate(instance=data, schema=research_input_schema)

    def test_config_invalid_mode_fails(self, research_input_schema: dict) -> None:
        """Invalid mode should fail."""
        data = {
            "claims": [{"text": "Test"}],
            "config": {"mode": "invalid"},
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=data, schema=research_input_schema)

    def test_config_runs_zero_fails(self, research_input_schema: dict) -> None:
        """runs=0 should fail (minimum 1)."""
        data = {
            "claims": [{"text": "Test"}],
            "config": {"runs": 0},
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=data, schema=research_input_schema)
