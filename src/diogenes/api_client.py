"""Anthropic API client for calling sub-agent prompts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import anthropic

from diogenes.config import ConfigError, DioConfig, load_config


class SubAgentError(Exception):
    """Raised when a sub-agent call fails."""

    def __init__(self, agent_name: str, message: str) -> None:
        """Initialize with the failing agent name and error message."""
        self.agent_name = agent_name
        super().__init__(f"Sub-agent '{agent_name}' failed: {message}")


class APIClient:
    """Thin wrapper around the Anthropic API for calling sub-agent prompts.

    Each sub-agent is a markdown prompt file. The client loads the prompt,
    sends it as the system message with the user input, and returns the
    parsed JSON response.
    """

    DEFAULT_MODEL = "claude-sonnet-4-20250514"
    DEFAULT_MAX_TOKENS = 8192

    def __init__(
        self,
        *,
        config: DioConfig | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> None:
        """Initialize the API client.

        Args:
            config: Pre-loaded configuration. If omitted, loads from all config sources
                (environment variable, .dorc files, .env file).
            model: Anthropic model ID. Overrides the value in config.
            max_tokens: Maximum response tokens. Defaults to 8192.

        Raises:
            SubAgentError: If configuration cannot be loaded (e.g., no API key found).

        """
        try:
            cfg = config if config is not None else load_config()
        except ConfigError as e:
            raise SubAgentError("config", str(e)) from e

        self._client = anthropic.Anthropic(api_key=cfg.api_key, base_url=cfg.base_url)
        self._model = model or cfg.model or self.DEFAULT_MODEL
        self._max_tokens = max_tokens or self.DEFAULT_MAX_TOKENS

    def call_sub_agent(
        self,
        *,
        prompt_path: str | Path,
        user_input: str | dict[str, Any],
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Call a sub-agent prompt and return parsed JSON.

        Args:
            prompt_path: Path to the sub-agent markdown prompt file.
            user_input: User input as JSON dict or raw text string.
            model: Override the default model for this call.
            max_tokens: Override the default max tokens for this call.

        Returns:
            Parsed JSON dict from the sub-agent response.

        Raises:
            SubAgentError: If the prompt file doesn't exist, the API
                call fails, or the response is not valid JSON.

        """
        prompt_file = Path(prompt_path)
        if not prompt_file.exists():
            msg = f"Prompt file not found: {prompt_file}"
            raise SubAgentError(prompt_file.stem, msg)

        system_prompt = prompt_file.read_text()

        # Convert dict input to JSON string
        user_message = json.dumps(user_input, indent=2) if isinstance(user_input, dict) else user_input

        try:
            response = self._client.messages.create(
                model=model or self._model,
                max_tokens=max_tokens or self._max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
        except anthropic.APIError as e:
            msg = f"API call failed: {e}"
            raise SubAgentError(prompt_file.stem, msg) from e

        # Extract text content from response
        text_content = ""
        for block in response.content:
            if block.type == "text":
                text_content += block.text

        if not text_content:
            msg = "Empty response from API"
            raise SubAgentError(prompt_file.stem, msg)

        # Parse JSON from response — handle markdown code blocks
        json_text = text_content.strip()
        if json_text.startswith("```"):
            # Strip markdown code fence
            lines = json_text.split("\n")
            # Remove first line (```json or ```) and last line (```)
            lines = [line for line in lines if not line.strip().startswith("```")]
            json_text = "\n".join(lines)

        try:
            result: dict[str, Any] = json.loads(json_text)
        except json.JSONDecodeError as e:
            msg = f"Response is not valid JSON: {e}\nRaw response:\n{text_content[:500]}"
            raise SubAgentError(prompt_file.stem, msg) from e

        return result
