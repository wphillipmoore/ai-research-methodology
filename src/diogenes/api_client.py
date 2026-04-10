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

    By default, the common guidelines (behavioral constraints, input types,
    researcher profile) are prepended to every sub-agent prompt. This ensures
    all sub-agents operate under the same non-negotiable rules regardless of
    which step they implement.
    """

    DEFAULT_MODEL = "claude-sonnet-4-20250514"
    DEFAULT_MAX_TOKENS = 8192
    _PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"
    _COMMON_GUIDELINES_PATH = _PROMPTS_DIR / "common-guidelines.md"

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
                (environment variable, .dorc files, .env file).
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

    def call_sub_agent(
        self,
        *,
        prompt_path: str | Path,
        user_input: str | dict[str, Any],
        model: str | None = None,
        max_tokens: int | None = None,
        include_guidelines: bool = True,
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

        agent_prompt = prompt_file.read_text()

        if include_guidelines and self._common_guidelines:
            system_prompt = self._common_guidelines + "\n\n---\n\n" + agent_prompt
        else:
            system_prompt = agent_prompt

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
