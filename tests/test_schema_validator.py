"""Tests for schema_validator module."""

import json
from pathlib import Path

import pytest

from diogenes.schema_validator import ValidationError, is_json, parse_input_file, validate, validate_research_input


class TestIsJson:
    """Tests for is_json."""

    def test_valid_object(self) -> None:
        assert is_json('{"key": "value"}') is True

    def test_valid_array(self) -> None:
        assert is_json("[1, 2, 3]") is True

    def test_invalid_json(self) -> None:
        assert is_json("not json at all") is False

    def test_empty_string(self) -> None:
        assert is_json("") is False

    def test_bare_string(self) -> None:
        assert is_json('"hello"') is True

    def test_number(self) -> None:
        assert is_json("42") is True

    def test_malformed(self) -> None:
        assert is_json("{key: value}") is False


class TestValidate:
    """Tests for validate function."""

    def test_valid_research_input(self) -> None:
        data = {"claims": [{"text": "A claim"}], "queries": []}
        result = validate(data, "research-input.schema.json")
        assert result == data

    def test_invalid_data_raises(self) -> None:
        with pytest.raises(ValidationError, match="research-input.schema.json"):
            validate({}, "research-input.schema.json")

    def test_nonexistent_schema_raises(self) -> None:
        with pytest.raises(ValidationError, match="not found"):
            validate({}, "nonexistent.schema.json")

    def test_validation_error_has_path(self) -> None:
        try:
            validate({"claims": [{}], "queries": []}, "research-input.schema.json")
        except ValidationError as e:
            assert e.schema_name == "research-input.schema.json"
            assert e.path  # Should have a JSON path


class TestValidateResearchInput:
    """Tests for validate_research_input."""

    def test_delegates_to_validate(self) -> None:
        data = {"claims": [], "queries": [{"text": "A query"}]}
        result = validate_research_input(data)
        assert result == data

    def test_raises_on_invalid(self) -> None:
        with pytest.raises(ValidationError):
            validate_research_input({})


class TestParseInputFile:
    """Tests for parse_input_file."""

    def test_json_file(self, tmp_path: Path) -> None:
        path = tmp_path / "input.json"
        path.write_text(json.dumps({"claims": [{"text": "Test"}]}))
        result = parse_input_file(path)
        assert isinstance(result, dict)
        assert result["claims"][0]["text"] == "Test"

    def test_text_file(self, tmp_path: Path) -> None:
        path = tmp_path / "input.md"
        path.write_text("Is AI reliable for fact-checking?")
        result = parse_input_file(path)
        assert isinstance(result, str)
        assert "reliable" in result

    def test_nonexistent_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError, match="not found"):
            parse_input_file("/tmp/does-not-exist.json")


class TestValidationError:
    """Tests for ValidationError class."""

    def test_with_path(self) -> None:
        err = ValidationError("test.schema.json", "bad value", path="items.0.text")
        assert "test.schema.json" in str(err)
        assert "items.0.text" in str(err)
        assert err.schema_name == "test.schema.json"
        assert err.path == "items.0.text"

    def test_without_path(self) -> None:
        err = ValidationError("test.schema.json", "bad value")
        assert "test.schema.json" in str(err)
        assert err.path == ""


class TestLoadSchemaInvalidJson:
    """Test _load_schema with invalid JSON content."""

    def test_invalid_json_schema_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from diogenes import schema_validator

        schema_dir = tmp_path / "schemas"
        schema_dir.mkdir()
        bad_schema = schema_dir / "bad.schema.json"
        bad_schema.write_text("not valid json {{{")
        monkeypatch.setattr(schema_validator, "_SCHEMAS_DIR", schema_dir)
        with pytest.raises(ValidationError, match="Invalid JSON"):
            validate({}, "bad.schema.json")


class TestUsageSchema:
    """Tests for usage.schema.json — verifies CLI and plugin shapes both validate."""

    def test_cli_shape_validates(self) -> None:
        """The CLI produces a detailed per_call breakdown; this shape must validate."""
        data = {
            "totals": {
                "input_tokens": 1000,
                "output_tokens": 500,
                "total_tokens": 1500,
                "web_search_requests": 3,
                "web_fetch_requests": 2,
                "api_calls": 5,
                "estimated_cost_usd": 0.012,
            },
            "per_call": [
                {
                    "agent": "hypothesis-gen",
                    "model": "claude-sonnet-4-6",
                    "input_tokens": 600,
                    "output_tokens": 300,
                    "cache_read_tokens": 200,
                    "estimated_cost_usd": 0.007,
                },
            ],
        }
        assert validate(data, "usage.schema.json") == data

    def test_plugin_shape_validates(self) -> None:
        """Plugin path: token fields zeroed, plugin_metadata carries extras.

        Claude Code does not expose token counts to skills, so the plugin
        fills unknowns with 0 and carries plugin-specific stats under the
        free-form `plugin_metadata` key.
        """
        data = {
            "totals": {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "web_search_requests": 7,
                "web_fetch_requests": 4,
                "api_calls": 0,
                "estimated_cost_usd": 0.0,
            },
            "per_call": [],
            "plugin_metadata": {
                "scoring_distribution": {"high": 3, "medium": 2, "low": 1},
                "verdict_summary": {"supported": 4, "contradicted": 1},
            },
        }
        assert validate(data, "usage.schema.json") == data

    def test_rejects_unknown_top_level_key(self) -> None:
        """Plugin extras must go under plugin_metadata, not as new top-level keys."""
        data = {
            "totals": {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "api_calls": 0,
                "estimated_cost_usd": 0.0,
            },
            "per_call": [],
            "custom_plugin_field": {"foo": "bar"},
        }
        with pytest.raises(ValidationError, match="usage.schema.json"):
            validate(data, "usage.schema.json")

    def test_rejects_missing_required_totals_field(self) -> None:
        """Totals.input_tokens remains required even when set to 0."""
        data = {
            "totals": {
                # missing input_tokens
                "output_tokens": 0,
                "total_tokens": 0,
                "api_calls": 0,
                "estimated_cost_usd": 0.0,
            },
            "per_call": [],
        }
        with pytest.raises(ValidationError, match="usage.schema.json"):
            validate(data, "usage.schema.json")

    def test_cli_accumulator_output_conforms(self) -> None:
        """Regression guard: UsageAccumulator.to_dict() output validates.

        Catches drift between api_client.UsageAccumulator and
        usage.schema.json — if either side changes, CI fails here.
        """
        from diogenes.api_client import CallUsage, UsageAccumulator

        acc = UsageAccumulator()
        acc.record(
            CallUsage(
                agent_name="hypothesis-gen",
                model="claude-sonnet-4-6",
                input_tokens=500,
                output_tokens=100,
                cache_read_tokens=200,
                web_search_requests=2,
            ),
        )
        validate(acc.to_dict(), "usage.schema.json")
