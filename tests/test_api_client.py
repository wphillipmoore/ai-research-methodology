"""Tests for api_client module."""

import json
from unittest.mock import MagicMock, patch

import pytest

from diogenes.api_client import (
    APIClient,
    CallUsage,
    SubAgentError,
    UsageAccumulator,
    _estimate_call_cost,
    _parse_json_response,
    _preview,
    _strip_to_schema,
    _validate_against_schema,
)
from diogenes.config import DioConfig


class TestCallUsage:
    """Tests for CallUsage dataclass."""

    def test_defaults(self) -> None:
        u = CallUsage(agent_name="test", model="sonnet")
        assert u.input_tokens == 0
        assert u.output_tokens == 0
        assert u.web_search_requests == 0
        assert u.service_tier == "standard"


class TestEstimateCallCost:
    """Tests for _estimate_call_cost."""

    def test_known_model(self) -> None:
        usage = CallUsage(
            agent_name="test",
            model="claude-sonnet-4-6",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
        cost = _estimate_call_cost(usage)
        assert cost == pytest.approx(18.0)  # 3.00 + 15.00

    def test_unknown_model_uses_default(self) -> None:
        usage = CallUsage(
            agent_name="test",
            model="unknown-model",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
        cost = _estimate_call_cost(usage)
        assert cost == pytest.approx(18.0)  # defaults to sonnet rates

    def test_web_search_cost(self) -> None:
        usage = CallUsage(
            agent_name="test",
            model="claude-sonnet-4-6",
            web_search_requests=100,
        )
        cost = _estimate_call_cost(usage)
        assert cost == pytest.approx(1.0)  # 100 * $0.01

    def test_zero_tokens(self) -> None:
        usage = CallUsage(agent_name="test", model="claude-sonnet-4-6")
        assert _estimate_call_cost(usage) == 0.0


class TestUsageAccumulator:
    """Tests for UsageAccumulator."""

    def test_empty(self) -> None:
        acc = UsageAccumulator()
        assert acc.total_input_tokens == 0
        assert acc.total_output_tokens == 0
        assert acc.total_tokens == 0
        assert acc.total_web_searches == 0
        assert acc.total_web_fetches == 0
        assert acc.total_estimated_cost == 0.0

    def test_record_and_totals(self) -> None:
        acc = UsageAccumulator()
        acc.record(CallUsage(agent_name="a", model="claude-sonnet-4-6", input_tokens=100, output_tokens=50))
        acc.record(CallUsage(agent_name="b", model="claude-sonnet-4-6", input_tokens=200, output_tokens=100))
        assert acc.total_input_tokens == 300
        assert acc.total_output_tokens == 150
        assert acc.total_tokens == 450

    def test_web_totals(self) -> None:
        acc = UsageAccumulator()
        acc.record(CallUsage(agent_name="a", model="m", web_search_requests=3, web_fetch_requests=5))
        acc.record(CallUsage(agent_name="b", model="m", web_search_requests=2, web_fetch_requests=1))
        assert acc.total_web_searches == 5
        assert acc.total_web_fetches == 6

    def test_to_dict(self) -> None:
        acc = UsageAccumulator()
        acc.record(CallUsage(agent_name="test", model="claude-sonnet-4-6", input_tokens=1000))
        d = acc.to_dict()
        assert d["totals"]["api_calls"] == 1
        assert d["totals"]["input_tokens"] == 1000
        assert len(d["per_call"]) == 1
        assert d["per_call"][0]["agent"] == "test"
        assert "estimated_cost_usd" in d["per_call"][0]


class TestSubAgentError:
    """Tests for SubAgentError."""

    def test_message(self) -> None:
        err = SubAgentError("hypothesis-gen", "API timeout")
        assert "hypothesis-gen" in str(err)
        assert "API timeout" in str(err)
        assert err.agent_name == "hypothesis-gen"


class TestParseJsonResponse:
    """Tests for _parse_json_response."""

    def test_plain_json(self) -> None:
        result = _parse_json_response('{"key": "value"}', "test")
        assert result == {"key": "value"}

    def test_code_fenced_json(self) -> None:
        text = '```json\n{"key": "value"}\n```'
        result = _parse_json_response(text, "test")
        assert result == {"key": "value"}

    def test_json_with_trailing_text(self) -> None:
        text = 'Here is my response:\n{"key": "value"}\nI hope this helps!'
        result = _parse_json_response(text, "test")
        assert result == {"key": "value"}

    def test_no_json_raises(self) -> None:
        with pytest.raises(SubAgentError, match="No JSON object"):
            _parse_json_response("just plain text", "test")

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(SubAgentError, match="Could not extract"):
            _parse_json_response("{invalid json}", "test")

    def test_nested_json(self) -> None:
        text = '{"outer": {"inner": [1, 2]}}'
        result = _parse_json_response(text, "test")
        assert result["outer"]["inner"] == [1, 2]

    def test_code_fence_with_language(self) -> None:
        text = '```json\n{"a": 1}\n```'
        result = _parse_json_response(text, "test")
        assert result == {"a": 1}

    def test_unbalanced_braces_raises(self) -> None:
        """Covers branch 160->173: for-loop exhaustion when braces never balance."""
        with pytest.raises(SubAgentError, match="Could not extract"):
            _parse_json_response("{unclosed", "test")

    def test_nested_braces_with_prefix(self) -> None:
        """Covers branch 165->160: depth != 0 at inner '}'."""
        text = 'Here is JSON: {"a": {"b": 1}} done'
        result = _parse_json_response(text, "test")
        assert result == {"a": {"b": 1}}


class TestStripToSchema:
    """Tests for _strip_to_schema."""

    def test_strips_extra_fields(self) -> None:
        schema = {"properties": {"name": {"type": "string"}}}
        data = {"name": "test", "extra": "field"}
        stripped = _strip_to_schema(data, schema)
        assert "extra" not in data
        assert data == {"name": "test"}
        assert len(stripped) == 1
        assert "extra" in stripped[0]

    def test_no_extra_fields(self) -> None:
        schema = {"properties": {"name": {"type": "string"}}}
        data = {"name": "test"}
        stripped = _strip_to_schema(data, schema)
        assert stripped == []
        assert data == {"name": "test"}

    def test_recursive_strip(self) -> None:
        schema = {
            "properties": {
                "nested": {
                    "properties": {"keep": {"type": "string"}},
                },
            },
        }
        data = {"nested": {"keep": "yes", "remove": "no"}}
        stripped = _strip_to_schema(data, schema)
        assert data == {"nested": {"keep": "yes"}}
        assert len(stripped) == 1

    def test_array_items(self) -> None:
        schema = {
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "properties": {"name": {"type": "string"}},
                    },
                },
            },
        }
        data = {"items": [{"name": "a", "extra": "b"}]}
        stripped = _strip_to_schema(data, schema)
        assert data == {"items": [{"name": "a"}]}
        assert len(stripped) == 1

    def test_ref_resolution(self) -> None:
        schema = {
            "properties": {
                "item": {"$ref": "#/$defs/Item"},
            },
            "$defs": {
                "Item": {
                    "properties": {"id": {"type": "string"}},
                },
            },
        }
        data = {"item": {"id": "1", "extra": "x"}}
        stripped = _strip_to_schema(data, schema)
        assert data == {"item": {"id": "1"}}
        assert len(stripped) == 1

    def test_non_dict_data(self) -> None:
        schema = {"properties": {"x": {}}}
        stripped = _strip_to_schema("not a dict", schema)
        assert stripped == []

    def test_no_properties(self) -> None:
        schema = {"type": "object"}
        data = {"anything": "goes"}
        stripped = _strip_to_schema(data, schema)
        assert stripped == []

    def test_ref_in_items(self) -> None:
        schema = {
            "properties": {
                "list": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/Entry"},
                },
            },
            "$defs": {
                "Entry": {
                    "properties": {"id": {"type": "string"}},
                },
            },
        }
        data = {"list": [{"id": "1", "extra": "x"}]}
        stripped = _strip_to_schema(data, schema)
        assert data == {"list": [{"id": "1"}]}

    def test_ref_at_top_level(self) -> None:
        schema = {
            "$ref": "#/$defs/Root",
            "$defs": {
                "Root": {
                    "properties": {"name": {"type": "string"}},
                },
            },
        }
        data = {"name": "ok", "extra": "strip"}
        stripped = _strip_to_schema(data, schema)
        assert data == {"name": "ok"}

    def test_ref_in_property(self) -> None:
        schema = {
            "properties": {
                "child": {"$ref": "#/$defs/Child"},
            },
            "$defs": {
                "Child": {
                    "properties": {"val": {"type": "string"}},
                },
            },
        }
        data = {"child": {"val": "ok", "extra": "strip"}}
        stripped = _strip_to_schema(data, schema)
        assert data == {"child": {"val": "ok"}}

    def test_array_with_non_dict_items(self) -> None:
        schema = {
            "properties": {
                "nums": {"type": "array", "items": {"type": "integer"}},
            },
        }
        data = {"nums": [1, 2, 3]}
        stripped = _strip_to_schema(data, schema)
        assert stripped == []


class TestPreview:
    """Tests for _preview."""

    def test_short_value(self) -> None:
        assert _preview("hello") == "hello"

    def test_long_value_truncated(self) -> None:
        result = _preview("x" * 200)
        assert result.endswith("...")
        assert len(result) == 83  # 80 + "..."


class TestValidateAgainstSchema:
    """Tests for _validate_against_schema."""

    def test_valid(self) -> None:
        schema = {"type": "object", "properties": {"x": {"type": "string"}}}
        _validate_against_schema({"x": "hello"}, schema, "test")

    def test_invalid_raises(self) -> None:
        schema = {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}
        with pytest.raises(SubAgentError, match="schema validation"):
            _validate_against_schema({}, schema, "test")


class TestAPIClient:
    """Tests for APIClient."""

    def _make_config(self) -> DioConfig:
        return DioConfig(api_key="test-key")

    def test_init_with_config(self, tmp_path: pytest.TempPathFactory) -> None:
        cfg = self._make_config()
        # Create a guidelines file so it can be loaded
        guidelines = tmp_path / "guidelines.md"  # type: ignore[operator]
        guidelines.write_text("# Guidelines\nBe nice.")
        client = APIClient(config=cfg, guidelines_path=guidelines)
        assert client.model == "claude-sonnet-4-6"

    def test_init_no_config_raises(self, monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        for var in ("SERPER_API_KEY", "BRAVE_API_KEY", "GOOGLE_API_KEY", "GOOGLE_SEARCH_ENGINE_ID"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SubAgentError, match="config"):
            APIClient()

    def test_model_override(self) -> None:
        cfg = self._make_config()
        client = APIClient(config=cfg, model="claude-haiku-4-5-20251001", guidelines_path="/dev/null")
        assert client.model == "claude-haiku-4-5-20251001"

    def test_pipeline_property_exposes_tunables(self) -> None:
        """client.pipeline is a shortcut to config.pipeline."""
        cfg = self._make_config()
        client = APIClient(config=cfg, guidelines_path="/dev/null")
        assert client.pipeline is cfg.pipeline
        # Defaults match the pre-#76 hard-coded values
        assert client.pipeline.relevance_threshold == 5
        assert client.pipeline.max_output_tokens == 8192

    def test_max_tokens_defaults_to_config(self) -> None:
        """APIClient picks up max_output_tokens from config.pipeline."""
        from diogenes.config import PipelineConfig

        cfg = DioConfig(api_key="k", pipeline=PipelineConfig(max_output_tokens=4096))
        client = APIClient(config=cfg, guidelines_path="/dev/null")
        assert client._max_tokens == 4096

    def test_max_tokens_explicit_overrides_config(self) -> None:
        """Explicit max_tokens on APIClient wins over config."""
        from diogenes.config import PipelineConfig

        cfg = DioConfig(api_key="k", pipeline=PipelineConfig(max_output_tokens=4096))
        client = APIClient(config=cfg, max_tokens=2048, guidelines_path="/dev/null")
        assert client._max_tokens == 2048

    def test_model_for_returns_override(self) -> None:
        """model_for returns the override when configured."""
        from diogenes.config import PipelineConfig

        cfg = DioConfig(
            api_key="k",
            pipeline=PipelineConfig(
                model_overrides={"relevance_scorer": "claude-haiku-4-5-20251001"},
            ),
        )
        client = APIClient(config=cfg, guidelines_path="/dev/null")
        assert client.model_for("relevance_scorer") == "claude-haiku-4-5-20251001"

    def test_model_for_falls_back_to_default(self) -> None:
        """model_for returns the client's default model when no override."""
        cfg = self._make_config()
        client = APIClient(config=cfg, guidelines_path="/dev/null")
        # No override configured for 'hypothesis_generator' → default model
        assert client.model_for("hypothesis_generator") == client.model

    def test_missing_guidelines_path(self) -> None:
        cfg = self._make_config()
        client = APIClient(config=cfg, guidelines_path="/nonexistent/guidelines.md")
        assert client._common_guidelines == ""

    @patch("diogenes.api_client.anthropic.Anthropic")
    def test_call_sub_agent_prompt_not_found(self, _mock_anthropic: MagicMock) -> None:
        cfg = self._make_config()
        client = APIClient(config=cfg, guidelines_path="/dev/null")
        with pytest.raises(SubAgentError, match="not found"):
            client.call_sub_agent(
                prompt_path="/nonexistent/prompt.md",
                user_input="test",
            )

    @patch("diogenes.api_client.anthropic.Anthropic")
    def test_call_sub_agent_success(self, mock_anthropic_cls: MagicMock, tmp_path: pytest.TempPathFactory) -> None:
        # Set up mock
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.model = "claude-sonnet-4-6"
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_response.usage.cache_creation_input_tokens = 0
        mock_response.usage.cache_read_input_tokens = 0
        mock_response.usage.server_tool_use = None
        mock_response.usage.service_tier = "standard"

        mock_block = MagicMock()
        mock_block.type = "text"
        mock_block.text = '{"result": "success"}'
        mock_response.content = [mock_block]
        mock_client.messages.create.return_value = mock_response

        # Create prompt file
        prompt = tmp_path / "test-prompt.md"  # type: ignore[operator]
        prompt.write_text("# Test Prompt\nDo stuff.")

        cfg = self._make_config()
        client = APIClient(config=cfg, guidelines_path="/dev/null")
        result = client.call_sub_agent(prompt_path=prompt, user_input="test input")

        assert result == {"result": "success"}
        assert len(client.usage.calls) == 1

    @patch("diogenes.api_client.anthropic.Anthropic")
    def test_call_sub_agent_with_dict_input(
        self, mock_anthropic_cls: MagicMock, tmp_path: pytest.TempPathFactory
    ) -> None:
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.model = "m"
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 5
        mock_response.usage.cache_creation_input_tokens = 0
        mock_response.usage.cache_read_input_tokens = 0
        mock_response.usage.server_tool_use = None
        mock_response.usage.service_tier = None
        mock_block = MagicMock()
        mock_block.type = "text"
        mock_block.text = '{"ok": true}'
        mock_response.content = [mock_block]
        mock_client.messages.create.return_value = mock_response

        prompt = tmp_path / "prompt.md"  # type: ignore[operator]
        prompt.write_text("Prompt")

        cfg = self._make_config()
        client = APIClient(config=cfg, guidelines_path="/dev/null")
        result = client.call_sub_agent(prompt_path=prompt, user_input={"key": "value"})
        assert result == {"ok": True}

    @patch("diogenes.api_client.anthropic.Anthropic")
    def test_call_sub_agent_api_error(self, mock_anthropic_cls: MagicMock, tmp_path: pytest.TempPathFactory) -> None:
        import anthropic

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.side_effect = anthropic.APIError(
            message="rate limited",
            request=MagicMock(),
            body=None,
        )

        prompt = tmp_path / "prompt.md"  # type: ignore[operator]
        prompt.write_text("Prompt")

        cfg = self._make_config()
        client = APIClient(config=cfg, guidelines_path="/dev/null")
        with pytest.raises(SubAgentError, match="API call failed"):
            client.call_sub_agent(prompt_path=prompt, user_input="test")

    @patch("diogenes.api_client.anthropic.Anthropic")
    def test_call_sub_agent_empty_response(
        self, mock_anthropic_cls: MagicMock, tmp_path: pytest.TempPathFactory
    ) -> None:
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.model = "m"
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 0
        mock_response.usage.cache_creation_input_tokens = 0
        mock_response.usage.cache_read_input_tokens = 0
        mock_response.usage.server_tool_use = None
        mock_response.usage.service_tier = None
        mock_response.content = []  # No content blocks
        mock_client.messages.create.return_value = mock_response

        prompt = tmp_path / "prompt.md"  # type: ignore[operator]
        prompt.write_text("Prompt")

        cfg = self._make_config()
        client = APIClient(config=cfg, guidelines_path="/dev/null")
        with pytest.raises(SubAgentError, match="Empty response"):
            client.call_sub_agent(prompt_path=prompt, user_input="test")

    @patch("diogenes.api_client.anthropic.Anthropic")
    def test_call_sub_agent_with_schema(self, mock_anthropic_cls: MagicMock, tmp_path: pytest.TempPathFactory) -> None:
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.model = "m"
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 5
        mock_response.usage.cache_creation_input_tokens = 0
        mock_response.usage.cache_read_input_tokens = 0
        mock_response.usage.server_tool_use = None
        mock_response.usage.service_tier = None

        # Return valid JSON matching the schema
        mock_block = MagicMock()
        mock_block.type = "text"
        mock_block.text = json.dumps({"claims": [], "queries": [{"text": "test"}]})
        mock_response.content = [mock_block]
        mock_client.messages.create.return_value = mock_response

        prompt = tmp_path / "prompt.md"  # type: ignore[operator]
        prompt.write_text("Prompt")

        cfg = self._make_config()
        client = APIClient(config=cfg, guidelines_path="/dev/null")
        result = client.call_sub_agent(
            prompt_path=prompt,
            user_input="test",
            output_schema="research-input.schema.json",
        )
        assert "queries" in result

    @patch("diogenes.api_client.anthropic.Anthropic")
    def test_call_sub_agent_schema_not_found(
        self, mock_anthropic_cls: MagicMock, tmp_path: pytest.TempPathFactory
    ) -> None:
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        prompt = tmp_path / "prompt.md"  # type: ignore[operator]
        prompt.write_text("Prompt")

        cfg = self._make_config()
        client = APIClient(config=cfg, guidelines_path="/dev/null")
        with pytest.raises(SubAgentError, match="schema not found"):
            client.call_sub_agent(
                prompt_path=prompt,
                user_input="test",
                output_schema="nonexistent.schema.json",
            )

    @patch("diogenes.api_client.anthropic.Anthropic")
    def test_call_sub_agent_with_guidelines(
        self, mock_anthropic_cls: MagicMock, tmp_path: pytest.TempPathFactory
    ) -> None:
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.model = "m"
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 5
        mock_response.usage.cache_creation_input_tokens = 0
        mock_response.usage.cache_read_input_tokens = 0
        mock_response.usage.server_tool_use = None
        mock_response.usage.service_tier = None
        mock_block = MagicMock()
        mock_block.type = "text"
        mock_block.text = '{"ok": true}'
        mock_response.content = [mock_block]
        mock_client.messages.create.return_value = mock_response

        prompt = tmp_path / "prompt.md"  # type: ignore[operator]
        prompt.write_text("Prompt")
        guidelines = tmp_path / "guidelines.md"  # type: ignore[operator]
        guidelines.write_text("# Guidelines")

        cfg = self._make_config()
        client = APIClient(config=cfg, guidelines_path=guidelines)
        result = client.call_sub_agent(prompt_path=prompt, user_input="test", include_guidelines=True)
        assert result == {"ok": True}

        # Verify system blocks include guidelines
        call_kwargs = mock_client.messages.create.call_args.kwargs
        system_blocks = call_kwargs["system"]
        assert len(system_blocks) == 2  # guidelines + prompt

    @patch("diogenes.api_client.anthropic.Anthropic")
    def test_call_sub_agent_no_guidelines(
        self, mock_anthropic_cls: MagicMock, tmp_path: pytest.TempPathFactory
    ) -> None:
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.model = "m"
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 5
        mock_response.usage.cache_creation_input_tokens = 0
        mock_response.usage.cache_read_input_tokens = 0
        mock_response.usage.server_tool_use = None
        mock_response.usage.service_tier = None
        mock_block = MagicMock()
        mock_block.type = "text"
        mock_block.text = '{"ok": true}'
        mock_response.content = [mock_block]
        mock_client.messages.create.return_value = mock_response

        prompt = tmp_path / "prompt.md"  # type: ignore[operator]
        prompt.write_text("Prompt")

        cfg = self._make_config()
        client = APIClient(config=cfg, guidelines_path="/dev/null")
        client.call_sub_agent(prompt_path=prompt, user_input="test", include_guidelines=False)

        call_kwargs = mock_client.messages.create.call_args.kwargs
        system_blocks = call_kwargs["system"]
        assert len(system_blocks) == 1  # prompt only

    @patch("diogenes.api_client.anthropic.Anthropic")
    def test_call_sub_agent_with_web_search(
        self, mock_anthropic_cls: MagicMock, tmp_path: pytest.TempPathFactory
    ) -> None:
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.model = "m"
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 5
        mock_response.usage.cache_creation_input_tokens = 0
        mock_response.usage.cache_read_input_tokens = 0
        mock_response.usage.server_tool_use = MagicMock()
        mock_response.usage.server_tool_use.web_search_requests = 3
        mock_response.usage.server_tool_use.web_fetch_requests = 1
        mock_response.usage.service_tier = None
        mock_block = MagicMock()
        mock_block.type = "text"
        mock_block.text = '{"ok": true}'
        mock_response.content = [mock_block]
        mock_client.messages.create.return_value = mock_response

        prompt = tmp_path / "prompt.md"  # type: ignore[operator]
        prompt.write_text("Prompt")

        cfg = self._make_config()
        client = APIClient(config=cfg, guidelines_path="/dev/null")
        client.call_sub_agent(prompt_path=prompt, user_input="test", enable_web_search=True)

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert "tools" in call_kwargs
        assert client.usage.total_web_searches == 3

    @patch("diogenes.api_client.anthropic.Anthropic")
    def test_call_sub_agent_schema_strip_and_validate(
        self, mock_anthropic_cls: MagicMock, tmp_path: pytest.TempPathFactory
    ) -> None:
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.model = "m"
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 5
        mock_response.usage.cache_creation_input_tokens = 0
        mock_response.usage.cache_read_input_tokens = 0
        mock_response.usage.server_tool_use = None
        mock_response.usage.service_tier = None

        # Return JSON with an extra field that should be stripped
        mock_block = MagicMock()
        mock_block.type = "text"
        mock_block.text = json.dumps(
            {
                "claims": [],
                "queries": [{"text": "test"}],
                "extra_field": "should be stripped",
            }
        )
        mock_response.content = [mock_block]
        mock_client.messages.create.return_value = mock_response

        prompt = tmp_path / "prompt.md"  # type: ignore[operator]
        prompt.write_text("Prompt")

        cfg = self._make_config()
        client = APIClient(config=cfg, guidelines_path="/dev/null")
        result = client.call_sub_agent(
            prompt_path=prompt,
            user_input="test",
            output_schema="research-input.schema.json",
        )
        # extra_field should have been stripped
        assert "extra_field" not in result

    @patch("diogenes.api_client.anthropic.Anthropic")
    def test_call_sub_agent_skips_non_text_blocks(
        self, mock_anthropic_cls: MagicMock, tmp_path: pytest.TempPathFactory
    ) -> None:
        """Covers branch 485->484: response contains non-text blocks."""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.model = "m"
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 5
        mock_response.usage.cache_creation_input_tokens = 0
        mock_response.usage.cache_read_input_tokens = 0
        mock_response.usage.server_tool_use = None
        mock_response.usage.service_tier = None

        # First block is tool_use (non-text), second is text
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = '{"result": "ok"}'
        mock_response.content = [tool_block, text_block]
        mock_client.messages.create.return_value = mock_response

        prompt = tmp_path / "prompt.md"  # type: ignore[operator]
        prompt.write_text("Prompt")

        cfg = self._make_config()
        client = APIClient(config=cfg, guidelines_path="/dev/null")
        result = client.call_sub_agent(prompt_path=prompt, user_input="test")
        assert result == {"result": "ok"}
