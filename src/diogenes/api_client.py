"""Anthropic API client for calling sub-agent prompts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anthropic
import jsonschema

from diogenes.config import ConfigError, DioConfig, load_config


@dataclass
class CallUsage:
    """Token and tool usage from a single API call."""

    agent_name: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    web_search_requests: int = 0
    web_fetch_requests: int = 0
    service_tier: str = "standard"


# Approximate per-token costs in USD (Anthropic API, standard tier)
# These are estimates for cost tracking — actual billing may vary.
_MODEL_COSTS: dict[str, tuple[float, float]] = {
    # Values are (input_cost_per_1M_tokens, output_cost_per_1M_tokens)
    "claude-sonnet-4-20250514": (3.00, 15.00),
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    "claude-opus-4-20250514": (15.00, 75.00),
}
_WEB_SEARCH_COST_PER_REQUEST = 0.01  # $10/1K searches


def _estimate_call_cost(call: CallUsage) -> float:
    """Estimate the USD cost of a single API call."""
    input_rate, output_rate = _MODEL_COSTS.get(
        call.model, (3.00, 15.00),  # default to Sonnet rates
    )
    token_cost = (
        call.input_tokens * input_rate / 1_000_000
        + call.output_tokens * output_rate / 1_000_000
    )
    search_cost = call.web_search_requests * _WEB_SEARCH_COST_PER_REQUEST
    return token_cost + search_cost


@dataclass
class UsageAccumulator:
    """Accumulates usage across all API calls in a session."""

    calls: list[CallUsage] = field(default_factory=list)

    def record(self, usage: CallUsage) -> None:
        """Record a single call's usage."""
        self.calls.append(usage)

    @property
    def total_input_tokens(self) -> int:
        """Total input tokens across all calls."""
        return sum(c.input_tokens for c in self.calls)

    @property
    def total_output_tokens(self) -> int:
        """Total output tokens across all calls."""
        return sum(c.output_tokens for c in self.calls)

    @property
    def total_tokens(self) -> int:
        """Total tokens (input + output) across all calls."""
        return self.total_input_tokens + self.total_output_tokens

    @property
    def total_web_searches(self) -> int:
        """Total web search requests across all calls."""
        return sum(c.web_search_requests for c in self.calls)

    @property
    def total_web_fetches(self) -> int:
        """Total web fetch requests across all calls."""
        return sum(c.web_fetch_requests for c in self.calls)

    @property
    def total_estimated_cost(self) -> float:
        """Total estimated USD cost across all calls."""
        return sum(_estimate_call_cost(c) for c in self.calls)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict for JSON output."""
        return {
            "totals": {
                "input_tokens": self.total_input_tokens,
                "output_tokens": self.total_output_tokens,
                "total_tokens": self.total_tokens,
                "web_search_requests": self.total_web_searches,
                "web_fetch_requests": self.total_web_fetches,
                "api_calls": len(self.calls),
                "estimated_cost_usd": round(self.total_estimated_cost, 4),
            },
            "per_call": [
                {
                    "agent": c.agent_name,
                    "model": c.model,
                    "input_tokens": c.input_tokens,
                    "output_tokens": c.output_tokens,
                    "cache_creation_tokens": c.cache_creation_tokens,
                    "cache_read_tokens": c.cache_read_tokens,
                    "web_search_requests": c.web_search_requests,
                    "web_fetch_requests": c.web_fetch_requests,
                    "service_tier": c.service_tier,
                    "estimated_cost_usd": round(_estimate_call_cost(c), 4),
                }
                for c in self.calls
            ],
        }


class SubAgentError(Exception):
    """Raised when a sub-agent call fails."""

    def __init__(self, agent_name: str, message: str) -> None:
        """Initialize with the failing agent name and error message."""
        self.agent_name = agent_name
        super().__init__(f"Sub-agent '{agent_name}' failed: {message}")


def _parse_json_response(text_content: str, agent_name: str) -> dict[str, Any]:
    """Parse JSON from a sub-agent response, handling markdown code fences."""
    json_text = text_content.strip()
    if json_text.startswith("```"):
        lines = json_text.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        json_text = "\n".join(lines)

    try:
        result: dict[str, Any] = json.loads(json_text)
    except json.JSONDecodeError as e:
        msg = f"Response is not valid JSON: {e}\nRaw response:\n{text_content[:500]}"
        raise SubAgentError(agent_name, msg) from e

    return result


def _validate_against_schema(
    result: dict[str, Any],
    schema_dict: dict[str, Any],
    agent_name: str,
) -> None:
    """Validate a parsed response against a JSON Schema."""
    try:
        jsonschema.validate(instance=result, schema=schema_dict)
    except jsonschema.ValidationError as e:
        path = ".".join(str(p) for p in e.absolute_path)
        msg = f"Response failed schema validation at '{path}': {e.message}"
        raise SubAgentError(agent_name, msg) from e


class APIClient:
    """Thin wrapper around the Anthropic API for calling sub-agent prompts.

    Each sub-agent is a markdown prompt file. The client loads the prompt,
    sends it as the system message with the user input, and returns the
    parsed JSON response.

    By default, the common guidelines (behavioral constraints, input types,
    researcher profile) are prepended to every sub-agent prompt. This ensures
    all sub-agents operate under the same non-negotiable rules regardless of
    which step they implement.
    """

    DEFAULT_MODEL = "claude-sonnet-4-20250514"
    DEFAULT_MAX_TOKENS = 8192
    _PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"
    _COMMON_GUIDELINES_PATH = _PROMPTS_DIR / "common-guidelines.md"
    _SCHEMAS_DIR = Path(__file__).parent / "schemas"

    def __init__(
        self,
        *,
        config: DioConfig | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        guidelines_path: str | Path | None = None,
    ) -> None:
        """Initialize the API client.

        Args:
            config: Pre-loaded configuration. If omitted, loads from all config sources
                (environment variable, .diorc files, .env file).
            model: Anthropic model ID. Overrides the value in config.
            max_tokens: Maximum response tokens. Defaults to 8192.
            guidelines_path: Path to common guidelines file. Defaults to
                prompts/common-guidelines.md in the repo root.

        Raises:
            SubAgentError: If configuration cannot be loaded (e.g., no API key found).

        """
        try:
            cfg = config if config is not None else load_config()
        except ConfigError as e:
            agent_name = "config"
            msg = str(e)
            raise SubAgentError(agent_name, msg) from e

        self._client = anthropic.Anthropic(api_key=cfg.api_key, base_url=cfg.base_url)
        self._model = model or cfg.model or self.DEFAULT_MODEL
        self._max_tokens = max_tokens or self.DEFAULT_MAX_TOKENS

        gp = Path(guidelines_path) if guidelines_path is not None else self._COMMON_GUIDELINES_PATH
        if gp.exists():
            self._common_guidelines = gp.read_text()
        else:
            self._common_guidelines = ""

        self.usage = UsageAccumulator()

    def _compose_system_prompt(
        self,
        agent_prompt: str,
        *,
        include_guidelines: bool,
        output_schema: str | None,
    ) -> tuple[str, dict[str, Any] | None]:
        """Compose the system prompt from guidelines, agent prompt, and schema.

        Returns:
            Tuple of (system_prompt, schema_dict or None).

        """
        parts = []
        if include_guidelines and self._common_guidelines:
            parts.append(self._common_guidelines)
        parts.append(agent_prompt)

        schema_dict: dict[str, Any] | None = None
        if output_schema:
            schema_path = self._SCHEMAS_DIR / output_schema
            if not schema_path.exists():
                agent_name = "schema"
                msg = f"Output schema not found: {schema_path}"
                raise SubAgentError(agent_name, msg)
            schema_text = schema_path.read_text()
            schema_dict = json.loads(schema_text)
            parts.append(
                "## Output JSON Schema\n\n"
                "Your output MUST conform to this JSON Schema. "
                "This is the canonical specification — if anything in the prompt "
                "above conflicts with this schema, the schema wins.\n\n"
                f"```json\n{schema_text}\n```"
            )

        return "\n\n---\n\n".join(parts), schema_dict

    def call_sub_agent(
        self,
        *,
        prompt_path: str | Path,
        user_input: str | dict[str, Any],
        model: str | None = None,
        max_tokens: int | None = None,
        include_guidelines: bool = True,
        output_schema: str | None = None,
        enable_web_search: bool = False,
    ) -> dict[str, Any]:
        """Call a sub-agent prompt and return parsed JSON.

        Args:
            prompt_path: Path to the sub-agent markdown prompt file.
            user_input: User input as JSON dict or raw text string.
            model: Override the default model for this call.
            max_tokens: Override the default max tokens for this call.
            include_guidelines: Prepend common behavioral guidelines to the
                system prompt. Defaults to True. Set to False only for purely
                mechanical steps that do not involve judgment or evidence handling.
            output_schema: Schema filename (e.g., 'hypotheses.schema.json') to
                append to the system prompt and validate the response against.
                Loaded from the schemas package directory.
            enable_web_search: Include the Anthropic web search server tool.
                When True, the model can execute web searches during the call.
                Anthropic handles search execution server-side.

        Returns:
            Parsed JSON dict from the sub-agent response.

        Raises:
            SubAgentError: If the prompt file doesn't exist, the API
                call fails, the response is not valid JSON, or the
                response does not conform to the output schema.

        """
        prompt_file = Path(prompt_path)
        if not prompt_file.exists():
            msg = f"Prompt file not found: {prompt_file}"
            raise SubAgentError(prompt_file.stem, msg)

        agent_prompt = prompt_file.read_text()
        system_prompt, schema_dict = self._compose_system_prompt(
            agent_prompt,
            include_guidelines=include_guidelines,
            output_schema=output_schema,
        )

        # Convert dict input to JSON string
        user_message = json.dumps(user_input, indent=2) if isinstance(user_input, dict) else user_input

        # Build API call kwargs
        api_kwargs: dict[str, Any] = {
            "model": model or self._model,
            "max_tokens": max_tokens or self._max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_message}],
        }

        if enable_web_search:
            api_kwargs["tools"] = [
                {
                    "type": "web_search_20260209",
                    "name": "web_search",
                    "allowed_callers": ["direct"],
                },
            ]

        try:
            response = self._client.messages.create(**api_kwargs)
        except anthropic.APIError as e:
            msg = f"API call failed: {e}"
            raise SubAgentError(prompt_file.stem, msg) from e

        # Record usage
        server_tool = response.usage.server_tool_use
        self.usage.record(CallUsage(
            agent_name=prompt_file.stem,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cache_creation_tokens=response.usage.cache_creation_input_tokens or 0,
            cache_read_tokens=response.usage.cache_read_input_tokens or 0,
            web_search_requests=server_tool.web_search_requests if server_tool else 0,
            web_fetch_requests=server_tool.web_fetch_requests if server_tool else 0,
            service_tier=response.usage.service_tier or "standard",
        ))

        # Extract text content from response
        text_content = ""
        for block in response.content:
            if block.type == "text":
                text_content += block.text

        if not text_content:
            msg = "Empty response from API"
            raise SubAgentError(prompt_file.stem, msg)

        result = _parse_json_response(text_content, prompt_file.stem)

        if schema_dict is not None:
            _validate_against_schema(result, schema_dict, prompt_file.stem)

        return result
