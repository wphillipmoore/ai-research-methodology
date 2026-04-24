"""Tests for config module."""

from pathlib import Path

import pytest

from diogenes.config import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    ConfigError,
    DioConfig,
    _find_dotenv,
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


class TestFindDotenv:
    """Tests for _find_dotenv upward-search behavior (issue #155)."""

    def test_found_in_cwd(self, tmp_path: Path) -> None:
        """.env present in the starting directory is returned immediately."""
        dotenv = tmp_path / ".env"
        dotenv.write_text("KEY=value\n")
        result = _find_dotenv(tmp_path)
        assert result == dotenv.resolve()

    def test_found_in_ancestor(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """.env in a parent directory is found via upward walk."""
        # Keep the walk away from $HOME / real repo boundaries by pinning
        # $HOME to somewhere unrelated.
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "nonexistent_home")
        ancestor = tmp_path / "repo"
        ancestor.mkdir()
        dotenv = ancestor / ".env"
        dotenv.write_text("KEY=value\n")
        deep = ancestor / "a" / "b" / "c"
        deep.mkdir(parents=True)
        result = _find_dotenv(deep)
        assert result == dotenv.resolve()

    def test_stops_at_git_boundary(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """The walk stops at a .git directory and does not cross into parents."""
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "nonexistent_home")
        # .env lives in tmp_path (the "parent repo"), but our starting
        # directory is inside a nested repo with its own .git.
        (tmp_path / ".env").write_text("SHOULD_NOT_BE_FOUND=1\n")
        nested_repo = tmp_path / "nested"
        nested_repo.mkdir()
        (nested_repo / ".git").mkdir()
        deep = nested_repo / "a" / "b"
        deep.mkdir(parents=True)
        result = _find_dotenv(deep)
        assert result is None

    def test_git_file_also_stops_walk(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """A .git FILE (worktree marker) also acts as a boundary."""
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "nonexistent_home")
        (tmp_path / ".env").write_text("SHOULD_NOT_BE_FOUND=1\n")
        worktree = tmp_path / "wt"
        worktree.mkdir()
        # git worktrees have a .git FILE, not a directory.
        (worktree / ".git").write_text("gitdir: /elsewhere\n")
        result = _find_dotenv(worktree)
        assert result is None

    def test_found_at_git_boundary_itself(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """If .env sits next to .git in the repo root, it is found there."""
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "nonexistent_home")
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".git").mkdir()
        dotenv = repo / ".env"
        dotenv.write_text("KEY=value\n")
        deep = repo / "a" / "b"
        deep.mkdir(parents=True)
        result = _find_dotenv(deep)
        assert result == dotenv.resolve()

    def test_stops_at_home(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """The walk stops at $HOME and does not look above it."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)
        # .env above $HOME should NOT be discovered.
        (tmp_path / ".env").write_text("ABOVE_HOME=1\n")
        deep = fake_home / "project" / "sub"
        deep.mkdir(parents=True)
        result = _find_dotenv(deep)
        assert result is None

    def test_not_found_at_all(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Returns None when no .env exists within the bounded walk."""
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "nonexistent_home")
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        result = _find_dotenv(deep)
        assert result is None

    def test_filesystem_root_stops_walk(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """When the walk reaches the filesystem root, it stops and returns None.

        We fake this by pointing $HOME somewhere that will never be hit
        (under tmp_path that doesn't exist) so the only stopping condition
        available up the tree from tmp_path is eventually the filesystem
        root.
        """
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "does-not-exist")
        deep = tmp_path / "x"
        deep.mkdir()
        # No .env, no .git, no home match -> walk must terminate at /.
        assert _find_dotenv(deep) is None


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

    def test_dotenv_found_in_ancestor(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """load_config() uses upward search to locate .env (issue #155)."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        for var in ("SERPER_API_KEY", "BRAVE_API_KEY", "GOOGLE_API_KEY", "GOOGLE_SEARCH_ENGINE_ID"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "nonexistent_home")
        # .env sits two levels up from our cwd.
        (tmp_path / ".env").write_text('ANTHROPIC_API_KEY="upward-key"\nSERPER_API_KEY="upward-serper"\n')
        deep = tmp_path / "a" / "b"
        deep.mkdir(parents=True)
        monkeypatch.chdir(deep)
        cfg = load_config()
        assert cfg.api_key == "upward-key"
        assert cfg.serper_api_key == "upward-serper"

    def test_dotenv_blocked_by_git_boundary(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """A .git boundary below the .env prevents discovery (issue #155)."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        for var in ("SERPER_API_KEY", "BRAVE_API_KEY", "GOOGLE_API_KEY", "GOOGLE_SEARCH_ENGINE_ID"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "nonexistent_home")
        # A .env in the outer dir that SHOULD NOT be picked up:
        (tmp_path / ".env").write_text('ANTHROPIC_API_KEY="outer-key"\n')
        # An inner "repo" with its own .git — dio should not cross this boundary.
        inner = tmp_path / "inner-repo"
        inner.mkdir()
        (inner / ".git").mkdir()
        monkeypatch.chdir(inner)
        with pytest.raises(ConfigError, match="No API key"):
            load_config()

    def test_explicit_dotenv_path_skips_upward_search(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Explicit [env] dotenv_path in .diorc is honored as-is (no upward search)."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        for var in ("SERPER_API_KEY", "BRAVE_API_KEY", "GOOGLE_API_KEY", "GOOGLE_SEARCH_ENGINE_ID"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "nonexistent_home")
        # Put a misleading .env in the ancestor that would normally be found.
        (tmp_path / ".env").write_text('ANTHROPIC_API_KEY="ancestor-key"\n')
        # Working dir has a .diorc that points at a specific file.
        workdir = tmp_path / "work"
        workdir.mkdir()
        explicit = workdir / "custom.env"
        explicit.write_text('ANTHROPIC_API_KEY="explicit-key"\n')
        diorc = workdir / ".diorc"
        diorc.write_text(f'[env]\ndotenv_path = "{explicit}"\n')
        monkeypatch.chdir(workdir)
        cfg = load_config()
        assert cfg.api_key == "explicit-key"

    def test_explicit_dotenv_path_missing_falls_through(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """If the explicit dotenv_path does not exist, it is silently skipped.

        We do not fall back to upward search in this case — the user asked
        for an explicit path; missing it should not silently surface an
        unrelated .env.
        """
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        for var in ("SERPER_API_KEY", "BRAVE_API_KEY", "GOOGLE_API_KEY", "GOOGLE_SEARCH_ENGINE_ID"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "nonexistent_home")
        # An ancestor .env that MUST NOT be picked up because the user
        # pointed us at an explicit (missing) path.
        (tmp_path / ".env").write_text('ANTHROPIC_API_KEY="should-not-be-found"\n')
        workdir = tmp_path / "work"
        workdir.mkdir()
        diorc = workdir / ".diorc"
        diorc.write_text('[env]\ndotenv_path = "/nonexistent/custom.env"\n')
        monkeypatch.chdir(workdir)
        with pytest.raises(ConfigError, match="No API key"):
            load_config()


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
