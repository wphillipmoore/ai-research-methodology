"""Diogenes configuration loading."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "https://api.anthropic.com"
DEFAULT_MODEL = "claude-sonnet-4-6"

# Pipeline tuning defaults. These match the values historically hard-coded
# across pipeline.py / api_client.py / search.py. Keeping them here lets
# .diorc override any of them without editing source.
_DEFAULT_RESULTS_PER_SEARCH = 5
_DEFAULT_SCORING_BATCH_SIZE = 5
_DEFAULT_RELEVANCE_THRESHOLD = 5
_DEFAULT_SEARCH_TERMS_PER_QUERY = 3
_DEFAULT_MAX_OUTPUT_TOKENS = 8192


class ConfigError(Exception):
    """Raised when Diogenes configuration cannot be resolved."""


@dataclass
class PipelineConfig:
    """Tunable pipeline parameters, overridable via ``[pipeline]`` in .diorc."""

    results_per_search: int = _DEFAULT_RESULTS_PER_SEARCH
    scoring_batch_size: int = _DEFAULT_SCORING_BATCH_SIZE
    relevance_threshold: int = _DEFAULT_RELEVANCE_THRESHOLD
    search_terms_per_query: int = _DEFAULT_SEARCH_TERMS_PER_QUERY
    max_output_tokens: int = _DEFAULT_MAX_OUTPUT_TOKENS
    # Per-agent model overrides keyed by logical sub-agent name (e.g.,
    # "relevance_scorer"). Absent keys fall back to the global ``model``
    # on DioConfig. See APIClient.model_for().
    model_overrides: dict[str, str] = field(default_factory=dict)


@dataclass
class DioConfig:
    """Resolved Diogenes runtime configuration."""

    api_key: str
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    search_provider: str = "serper"
    serper_api_key: str = ""
    brave_api_key: str = ""
    google_api_key: str = ""
    google_search_engine_id: str = ""
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)


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
    2. ``ANTHROPIC_API_KEY`` from ``.env`` file in the current directory
    3. ``api.key`` in ``./.diorc`` (project-level config, current directory)
    4. ``api.key`` in ``~/.diorc`` (user-level config)

    The ``.env`` file follows standard Python convention (VS Code, Docker
    Compose, etc.): values are loaded as pseudo-environment variables and
    override config files, but real environment variables override ``.env``.

    Returns:
        Resolved :class:`DioConfig` instance.

    Raises:
        ConfigError: If no API key can be resolved from any source.

    """
    user_toml = _load_toml(Path.home() / ".diorc")
    project_toml = _load_toml(Path.cwd() / ".diorc")

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

    # Load .env file (priority 2 — overrides .diorc but not env vars)
    dotenv_vars: dict[str, str] = {}
    if load_dotenv:
        dotenv_name = str(env_sect.get("dotenv_path", ".env"))
        dotenv_path = Path(dotenv_name)
        if dotenv_path.exists():
            dotenv_vars = _parse_dotenv(dotenv_path)

    # Priority 1: environment variable
    api_key: str = os.environ.get("ANTHROPIC_API_KEY", "")

    # Priority 2: .env file
    if not api_key:
        api_key = dotenv_vars.get("ANTHROPIC_API_KEY", "")

    # Priority 3 & 4: config file key (project or user .diorc)
    if not api_key:
        api_key = str(api_sect.get("key", ""))

    if not api_key:
        msg = "No API key found. Set ANTHROPIC_API_KEY, add api.key to .diorc, or create a .env file."
        raise ConfigError(msg)

    # Search provider configuration
    search_sect = _section(toml, "search")
    search_provider = str(search_sect.get("provider", "serper"))

    # Search API keys: env var > .env > .diorc (same priority as ANTHROPIC_API_KEY)
    serper_api_key = (
        os.environ.get("SERPER_API_KEY", "")
        or dotenv_vars.get("SERPER_API_KEY", "")
        or str(search_sect.get("serper_api_key", ""))
    )
    brave_api_key = (
        os.environ.get("BRAVE_API_KEY", "")
        or dotenv_vars.get("BRAVE_API_KEY", "")
        or str(search_sect.get("brave_api_key", ""))
    )
    google_api_key = (
        os.environ.get("GOOGLE_API_KEY", "")
        or dotenv_vars.get("GOOGLE_API_KEY", "")
        or str(search_sect.get("google_api_key", ""))
    )
    google_search_engine_id = (
        os.environ.get("GOOGLE_SEARCH_ENGINE_ID", "")
        or dotenv_vars.get("GOOGLE_SEARCH_ENGINE_ID", "")
        or str(search_sect.get("google_search_engine_id", ""))
    )

    pipeline_cfg = _load_pipeline_config(toml)

    return DioConfig(
        api_key=api_key,
        base_url=base_url,
        model=model,
        search_provider=search_provider,
        serper_api_key=serper_api_key,
        brave_api_key=brave_api_key,
        google_api_key=google_api_key,
        google_search_engine_id=google_search_engine_id,
        pipeline=pipeline_cfg,
    )


def _load_pipeline_config(toml: dict[str, Any]) -> PipelineConfig:
    """Build a PipelineConfig from the ``[pipeline]`` section of .diorc.

    Any field not present in the TOML falls back to the dataclass default.
    Model overrides come from the nested ``[pipeline.model_overrides]``
    subtable and are stored as a ``dict[str, str]``.
    """
    pipeline_sect = _section(toml, "pipeline")
    overrides_raw = pipeline_sect.get("model_overrides", {})
    model_overrides = {str(k): str(v) for k, v in overrides_raw.items()} if isinstance(overrides_raw, dict) else {}

    cfg = PipelineConfig(model_overrides=model_overrides)
    for field_name in (
        "results_per_search",
        "scoring_batch_size",
        "relevance_threshold",
        "search_terms_per_query",
        "max_output_tokens",
    ):
        if field_name in pipeline_sect:
            setattr(cfg, field_name, int(pipeline_sect[field_name]))
    return cfg
