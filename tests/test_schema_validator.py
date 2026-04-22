"""Tests for schema_validator module."""

import json

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

    def test_json_file(self, tmp_path: pytest.TempPathFactory) -> None:
        path = tmp_path / "input.json"  # type: ignore[operator]
        path.write_text(json.dumps({"claims": [{"text": "Test"}]}))
        result = parse_input_file(path)
        assert isinstance(result, dict)
        assert result["claims"][0]["text"] == "Test"

    def test_text_file(self, tmp_path: pytest.TempPathFactory) -> None:
        path = tmp_path / "input.md"  # type: ignore[operator]
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

    def test_invalid_json_schema_file(self, tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
        from diogenes import schema_validator

        schema_dir = tmp_path / "schemas"  # type: ignore[operator]
        schema_dir.mkdir()
        bad_schema = schema_dir / "bad.schema.json"
        bad_schema.write_text("not valid json {{{")
        monkeypatch.setattr(schema_validator, "_SCHEMAS_DIR", schema_dir)
        with pytest.raises(ValidationError, match="Invalid JSON"):
            validate({}, "bad.schema.json")
