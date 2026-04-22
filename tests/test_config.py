"""Tests for config module."""

from pathlib import Path

import pytest

from diogenes.config import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    ConfigError,
    DioConfig,
    _load_toml,
    _parse_dotenv,
    _section,
    load_config,
)


class TestParseDotenv:
    """Tests for _parse_dotenv."""

    def test_basic_key_value(self, tmp_path: Path) -> None:
        path = tmp_path / ".env"
        path.write_text("KEY=value\n")
        assert _parse_dotenv(path) == {"KEY": "value"}

    def test_double_quoted(self, tmp_path: Path) -> None:
        path = tmp_path / ".env"
        path.write_text('KEY="quoted value"\n')
        assert _parse_dotenv(path) == {"KEY": "quoted value"}

    def test_single_quoted(self, tmp_path: Path) -> None:
        path = tmp_path / ".env"
        path.write_text("KEY='single quoted'\n")
        assert _parse_dotenv(path) == {"KEY": "single quoted"}

    def test_export_prefix(self, tmp_path: Path) -> None:
        path = tmp_path / ".env"
        path.write_text("export KEY=value\n")
        assert _parse_dotenv(path) == {"KEY": "value"}

    def test_comments_and_empty_lines(self, tmp_path: Path) -> None:
        path = tmp_path / ".env"
        path.write_text("# comment\n\nKEY=value\n# another\n")
        assert _parse_dotenv(path) == {"KEY": "value"}

    def test_no_equals_sign_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / ".env"
        path.write_text("NOEQUALS\nKEY=value\n")
        assert _parse_dotenv(path) == {"KEY": "value"}

    def test_multiple_keys(self, tmp_path: Path) -> None:
        path = tmp_path / ".env"
        path.write_text("A=1\nB=2\nC=3\n")
        assert _parse_dotenv(path) == {"A": "1", "B": "2", "C": "3"}

    def test_value_with_equals(self, tmp_path: Path) -> None:
        path = tmp_path / ".env"
        path.write_text("KEY=value=with=equals\n")
        assert _parse_dotenv(path) == {"KEY": "value=with=equals"}

    def test_short_quoted_value_not_stripped(self, tmp_path: Path) -> None:
        path = tmp_path / ".env"
        path.write_text('KEY=""\n')
        assert _parse_dotenv(path) == {"KEY": ""}

    def test_single_char_value(self, tmp_path: Path) -> None:
        path = tmp_path / ".env"
        path.write_text("KEY=x\n")
        assert _parse_dotenv(path) == {"KEY": "x"}


class TestLoadToml:
    """Tests for _load_toml."""

    def test_existing_file(self, tmp_path: Path) -> None:
        path = tmp_path / "test.toml"
        path.write_text('[api]\nkey = "test-key"\n')
        result = _load_toml(path)
        assert result["api"]["key"] == "test-key"

    def test_missing_file(self, tmp_path: Path) -> None:
        path = tmp_path / "missing.toml"
        assert _load_toml(path) == {}


class TestSection:
    """Tests for _section."""

    def test_existing_section(self) -> None:
        toml = {"api": {"key": "val"}}
        assert _section(toml, "api") == {"key": "val"}

    def test_missing_section(self) -> None:
        assert _section({}, "api") == {}

    def test_non_dict_section(self) -> None:
        toml = {"api": "not a dict"}
        assert _section(toml, "api") == {}


class TestDioConfig:
    """Tests for DioConfig dataclass."""

    def test_defaults(self) -> None:
        cfg = DioConfig(api_key="test")
        assert cfg.base_url == DEFAULT_BASE_URL
        assert cfg.model == DEFAULT_MODEL
        assert cfg.search_provider == "serper"
        assert cfg.serper_api_key == ""


class TestLoadConfig:
    """Tests for load_config."""

    def test_from_env_var(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
        monkeypatch.chdir(tmp_path)
        cfg = load_config()
        assert cfg.api_key == "env-key"

    def test_from_dotenv(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.chdir(tmp_path)
        dotenv = tmp_path / ".env"
        dotenv.write_text('ANTHROPIC_API_KEY="dotenv-key"\n')
        cfg = load_config()
        assert cfg.api_key == "dotenv-key"

    def test_from_diorc(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.chdir(tmp_path)
        diorc = tmp_path / ".diorc"
        diorc.write_text('[api]\nkey = "diorc-key"\n')
        cfg = load_config()
        assert cfg.api_key == "diorc-key"

    def test_no_key_raises(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        # Clear all search-related env vars too
        for var in ("SERPER_API_KEY", "BRAVE_API_KEY", "GOOGLE_API_KEY", "GOOGLE_SEARCH_ENGINE_ID"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.chdir(tmp_path)
        with pytest.raises(ConfigError, match="No API key"):
            load_config()

    def test_env_overrides_dotenv(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "env-wins")
        monkeypatch.chdir(tmp_path)
        dotenv = tmp_path / ".env"
        dotenv.write_text('ANTHROPIC_API_KEY="dotenv-loses"\n')
        cfg = load_config()
        assert cfg.api_key == "env-wins"

    def test_project_diorc_overrides_user(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
        monkeypatch.chdir(tmp_path)
        # User-level config
        user_diorc = tmp_path / "userhome" / ".diorc"
        user_diorc.parent.mkdir()
        user_diorc.write_text('[api]\nmodel = "user-model"\n')
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "userhome")
        # Project-level config
        project_diorc = tmp_path / ".diorc"
        project_diorc.write_text('[api]\nmodel = "project-model"\n')
        cfg = load_config()
        assert cfg.model == "project-model"

    def test_search_provider_config(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
        monkeypatch.setenv("SERPER_API_KEY", "serper-key")
        monkeypatch.chdir(tmp_path)
        cfg = load_config()
        assert cfg.serper_api_key == "serper-key"

    def test_search_keys_from_dotenv(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        for var in ("SERPER_API_KEY", "BRAVE_API_KEY", "GOOGLE_API_KEY", "GOOGLE_SEARCH_ENGINE_ID"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.chdir(tmp_path)
        dotenv = tmp_path / ".env"
        dotenv.write_text(
            "ANTHROPIC_API_KEY=key\n"
            "SERPER_API_KEY=s-key\n"
            "BRAVE_API_KEY=b-key\n"
            "GOOGLE_API_KEY=g-key\n"
            "GOOGLE_SEARCH_ENGINE_ID=g-cx\n"
        )
        cfg = load_config()
        assert cfg.serper_api_key == "s-key"
        assert cfg.brave_api_key == "b-key"
        assert cfg.google_api_key == "g-key"
        assert cfg.google_search_engine_id == "g-cx"

    def test_load_dotenv_disabled(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.chdir(tmp_path)
        # .diorc disables dotenv loading but provides key
        diorc = tmp_path / ".diorc"
        diorc.write_text('[api]\nkey = "diorc-key"\n\n[env]\nload_dotenv = false\n')
        # .env exists but should be ignored
        dotenv = tmp_path / ".env"
        dotenv.write_text('ANTHROPIC_API_KEY="should-be-ignored"\n')
        cfg = load_config()
        assert cfg.api_key == "diorc-key"

    def test_search_provider_from_diorc(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
        monkeypatch.chdir(tmp_path)
        diorc = tmp_path / ".diorc"
        diorc.write_text('[search]\nprovider = "brave"\n')
        cfg = load_config()
        assert cfg.search_provider == "brave"

    def test_base_url_from_diorc(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
        monkeypatch.chdir(tmp_path)
        diorc = tmp_path / ".diorc"
        diorc.write_text('[api]\nbase_url = "https://custom.api.com"\n')
        cfg = load_config()
        assert cfg.base_url == "https://custom.api.com"


class TestPipelineConfig:
    """Tests for the [pipeline] section in .diorc."""

    def test_defaults_when_section_missing(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Omitting [pipeline] falls back to the dataclass defaults."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
        monkeypatch.chdir(tmp_path)
        cfg = load_config()
        # The defaults match the hard-coded values from before this PR.
        assert cfg.pipeline.results_per_search == 5
        assert cfg.pipeline.scoring_batch_size == 5
        assert cfg.pipeline.relevance_threshold == 5
        assert cfg.pipeline.search_terms_per_query == 3
        assert cfg.pipeline.max_output_tokens == 8192
        assert cfg.pipeline.model_overrides == {}

    def test_fields_override_defaults(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """[pipeline] fields in .diorc override the dataclass defaults."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
        monkeypatch.chdir(tmp_path)
        diorc = tmp_path / ".diorc"
        diorc.write_text(
            "[pipeline]\n"
            "results_per_search = 10\n"
            "scoring_batch_size = 7\n"
            "relevance_threshold = 6\n"
            "search_terms_per_query = 4\n"
            "max_output_tokens = 16384\n"
        )
        cfg = load_config()
        assert cfg.pipeline.results_per_search == 10
        assert cfg.pipeline.scoring_batch_size == 7
        assert cfg.pipeline.relevance_threshold == 6
        assert cfg.pipeline.search_terms_per_query == 4
        assert cfg.pipeline.max_output_tokens == 16384

    def test_model_overrides_parsed(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """[pipeline.model_overrides] becomes a dict[str, str]."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
        monkeypatch.chdir(tmp_path)
        diorc = tmp_path / ".diorc"
        diorc.write_text(
            "[pipeline.model_overrides]\n"
            'relevance_scorer = "claude-haiku-4-5-20251001"\n'
            'clarifier = "claude-sonnet-4-6"\n'
        )
        cfg = load_config()
        assert cfg.pipeline.model_overrides == {
            "relevance_scorer": "claude-haiku-4-5-20251001",
            "clarifier": "claude-sonnet-4-6",
        }

    def test_model_overrides_non_dict_falls_back_to_empty(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """If model_overrides is not a table (malformed .diorc), treat as empty."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
        monkeypatch.chdir(tmp_path)
        diorc = tmp_path / ".diorc"
        # Writing model_overrides as a string (not a table) is technically valid TOML
        # but not what we expect; should gracefully fall back.
        diorc.write_text('[pipeline]\nmodel_overrides = "not-a-table"\n')
        cfg = load_config()
        assert cfg.pipeline.model_overrides == {}
