"""Diogenes configuration loading."""

from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "https://api.anthropic.com"
DEFAULT_MODEL = "claude-sonnet-4-20250514"


class ConfigError(Exception):
    """Raised when Diogenes configuration cannot be resolved."""


@dataclass
class DioConfig:
    """Resolved Diogenes runtime configuration."""

    api_key: str
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL


def _parse_dotenv(path: Path) -> dict[str, str]:
    """Parse a .env file and return key-value pairs.

    Handles comments, empty lines, ``KEY=value``, ``KEY="value"``, and ``export KEY=value``.
    """
    result: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        line = stripped.removeprefix("export ").strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        _min_quoted_len = 2
        if len(value) >= _min_quoted_len and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        result[key] = value
    return result


def _load_toml(path: Path) -> dict[str, Any]:
    """Load a TOML file and return its contents, or an empty dict if not found."""
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _section(toml: dict[str, Any], key: str) -> dict[str, Any]:
    """Extract a named section from a TOML dict, returning empty dict if absent or wrong type."""
    value = toml.get(key, {})
    return value if isinstance(value, dict) else {}


def load_config() -> DioConfig:
    """Load Diogenes configuration from all sources in priority order.

    Priority (highest to lowest):

    1. ``ANTHROPIC_API_KEY`` environment variable
    2. ``api.key`` in ``./.dorc`` (project-level config, current directory)
    3. ``api.key`` in ``~/.dorc`` (user-level config)
    4. ``ANTHROPIC_API_KEY`` from ``.env`` file in the current directory (loaded with a warning)

    Returns:
        Resolved :class:`DioConfig` instance.

    Raises:
        ConfigError: If no API key can be resolved from any source.

    """
    user_toml = _load_toml(Path.home() / ".dorc")
    project_toml = _load_toml(Path.cwd() / ".dorc")

    # Merge: project-level overrides user-level, section by section
    toml: dict[str, Any] = {**user_toml}
    for k, v in project_toml.items():
        if isinstance(v, dict) and isinstance(toml.get(k), dict):
            toml[k] = {**toml[k], **v}
        else:
            toml[k] = v

    api_sect = _section(toml, "api")
    env_sect = _section(toml, "env")

    base_url = str(api_sect.get("base_url", DEFAULT_BASE_URL))
    model = str(api_sect.get("model", DEFAULT_MODEL))
    load_dotenv = bool(env_sect.get("load_dotenv", True))

    # Priority 1: environment variable
    api_key: str = os.environ.get("ANTHROPIC_API_KEY", "")

    # Priority 2 & 3: config file key (project or user .dorc)
    if not api_key:
        api_key = str(api_sect.get("key", ""))

    # Priority 4: .env file, with an explicit warning so it is never silent
    if not api_key and load_dotenv:
        dotenv_name = str(env_sect.get("dotenv_path", ".env"))
        dotenv_path = Path(dotenv_name)
        if dotenv_path.exists():
            sys.stderr.write(f"Warning: Loading API key from {dotenv_path.resolve()}\n")
            api_key = _parse_dotenv(dotenv_path).get("ANTHROPIC_API_KEY", "")

    if not api_key:
        msg = (
            "No API key found. "
            "Set ANTHROPIC_API_KEY, add api.key to .dorc, or create a .env file."
        )
        raise ConfigError(msg)

    return DioConfig(api_key=api_key, base_url=base_url, model=model)
