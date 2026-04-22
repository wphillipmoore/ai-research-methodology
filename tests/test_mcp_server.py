"""Tests for mcp_server module."""

import json
from unittest.mock import MagicMock, patch

import pytest

from diogenes.content_cache import reset_content_cache
from diogenes.events import reset_mcp_logger


class TestDioInitRun:
    """Tests for dio_init_run tool."""

    def setup_method(self) -> None:
        reset_mcp_logger()
        reset_content_cache()

    def teardown_method(self) -> None:
        reset_mcp_logger()
        reset_content_cache()

    def test_initializes(self, tmp_path: pytest.TempPathFactory) -> None:
        from diogenes.mcp_server import dio_init_run

        result = json.loads(dio_init_run(str(tmp_path), "run-1"))
        assert result["initialized"] is True
        assert result["run_id"] == "run-1"

    def test_resets_logger(self, tmp_path: pytest.TempPathFactory) -> None:
        from diogenes.events import get_mcp_logger
        from diogenes.mcp_server import dio_init_run

        logger = get_mcp_logger()
        logger.log(step="s", kind="k", detail="d", layer="l")
        dio_init_run(str(tmp_path), "run-2")
        new_logger = get_mcp_logger()
        assert len(new_logger.events) == 0
        assert new_logger.run_id == "run-2"


class TestDioNextStep:
    """Tests for dio_next_step tool."""

    def test_first_step(self, tmp_path: pytest.TempPathFactory) -> None:
        from diogenes.mcp_server import dio_next_step

        run_dir = tmp_path / "run-1"  # type: ignore[operator]
        run_dir.mkdir()
        result = json.loads(dio_next_step(str(run_dir)))
        assert result["step"] == "step_01_research_input_clarified"
        assert result["status"] == "ready"

    def test_all_complete(self, tmp_path: pytest.TempPathFactory) -> None:
        from diogenes.mcp_server import dio_next_step
        from diogenes.state_machine import PIPELINE_STEPS, PipelineState

        run_dir = tmp_path / "run-1"  # type: ignore[operator]
        run_dir.mkdir()
        state = PipelineState(run_dir)
        for step in PIPELINE_STEPS:
            state.mark_complete(step.name)
        result = json.loads(dio_next_step(str(run_dir)))
        assert result["step"] == "complete"
        assert result["status"] == "all_steps_done"

    def test_nonexistent_dir(self) -> None:
        from diogenes.mcp_server import dio_next_step

        result = json.loads(dio_next_step("/nonexistent/path"))
        assert result["error"] is True

    def test_python_only_step(self, tmp_path: pytest.TempPathFactory) -> None:
        from diogenes.mcp_server import dio_next_step
        from diogenes.state_machine import PIPELINE_STEPS, PipelineState

        run_dir = tmp_path / "run-1"  # type: ignore[operator]
        run_dir.mkdir()
        state = PipelineState(run_dir)
        # Complete all steps up to step_10_archive (which is python_only)
        for step in PIPELINE_STEPS[:9]:
            state.mark_complete(step.name)
            if step.output_file:
                (run_dir / step.output_file).write_text("{}")
        result = json.loads(dio_next_step(str(run_dir)))
        assert result["step"] == "step_10_archive"
        assert "dio_execute_step" in result["instructions"]

    def test_step_with_post_validators(self, tmp_path: pytest.TempPathFactory) -> None:
        from diogenes.mcp_server import dio_next_step
        from diogenes.state_machine import PIPELINE_STEPS, PipelineState

        run_dir = tmp_path / "run-1"  # type: ignore[operator]
        run_dir.mkdir()
        state = PipelineState(run_dir)
        # Complete up to step_06 (evidence_packets has post_validators)
        for step in PIPELINE_STEPS[:5]:
            state.mark_complete(step.name)
            if step.output_file:
                (run_dir / step.output_file).write_text("{}")
        result = json.loads(dio_next_step(str(run_dir)))
        assert result["step"] == "step_06_evidence_packets"
        assert "post_step" in result

    def test_step_without_prompt_non_python(self, tmp_path: pytest.TempPathFactory) -> None:
        """Covers line 142: step with category != python_only and no prompt field."""
        from diogenes.mcp_server import dio_next_step
        from diogenes.state_machine import StepDefinition

        run_dir = tmp_path / "run-1"  # type: ignore[operator]
        run_dir.mkdir()

        # Create a custom step with category="hybrid" but no prompt
        fake_step = StepDefinition(
            name="step_99_custom",
            display_name="Custom Step",
            output_file="custom.json",
            category="hybrid",
            prompt=None,
        )
        with patch("diogenes.mcp_server.PipelineState") as mock_state_cls:
            mock_state = MagicMock()
            mock_state.next_step.return_value = fake_step
            mock_state.summary.return_value = {"total_steps": 1, "completed": 0, "failed": 0, "remaining": 1}
            mock_state_cls.return_value = mock_state
            result = json.loads(dio_next_step(str(run_dir)))
        assert "dio_execute_step" in result["instructions"]

    def test_step_with_mcp_tools(self, tmp_path: pytest.TempPathFactory) -> None:
        from diogenes.mcp_server import dio_next_step
        from diogenes.state_machine import PIPELINE_STEPS, PipelineState

        run_dir = tmp_path / "run-1"  # type: ignore[operator]
        run_dir.mkdir()
        state = PipelineState(run_dir)
        # Complete up to step_04 (search_results) so step_05 (scorecards) is next — has mcp_tools
        for step in PIPELINE_STEPS[:4]:
            state.mark_complete(step.name)
            if step.output_file:
                (run_dir / step.output_file).write_text("{}")
        result = json.loads(dio_next_step(str(run_dir)))
        assert result["step"] == "step_05_scorecards"
        assert "required_tools" in result


class TestDioExecuteStep:
    """Tests for dio_execute_step tool."""

    def test_unknown_step(self, tmp_path: pytest.TempPathFactory) -> None:
        from diogenes.mcp_server import dio_execute_step

        run_dir = tmp_path / "run-1"  # type: ignore[operator]
        run_dir.mkdir()
        result = json.loads(dio_execute_step(str(run_dir), "nonexistent_step"))
        assert result["error"] is True

    def test_llm_step_rejected(self, tmp_path: pytest.TempPathFactory) -> None:
        from diogenes.mcp_server import dio_execute_step

        run_dir = tmp_path / "run-1"  # type: ignore[operator]
        run_dir.mkdir()
        result = json.loads(dio_execute_step(str(run_dir), "step_02_hypotheses"))
        assert result["error"] is True
        assert "llm" in result["message"].lower()

    def test_python_only_step(self, tmp_path: pytest.TempPathFactory) -> None:
        from diogenes.mcp_server import dio_execute_step

        run_dir = tmp_path / "run-1"  # type: ignore[operator]
        run_dir.mkdir()
        result = json.loads(dio_execute_step(str(run_dir), "step_10_archive"))
        assert result["executed"] is True


class TestDioSearch:
    """Tests for dio_search tool."""

    @patch("diogenes.mcp_server._create_search_provider")
    def test_search_success(self, mock_create: MagicMock) -> None:
        from diogenes.mcp_server import dio_search
        from diogenes.search import SearchResult

        mock_provider = MagicMock()
        mock_provider.name = "serper"
        mock_provider.search.return_value = (
            [SearchResult(title="T", url="https://a.com", snippet="S", page_age="2024")],
            1,
        )
        mock_create.return_value = mock_provider

        result = json.loads(dio_search("test query", 5))
        assert result["provider"] == "serper"
        assert len(result["results"]) == 1

    @patch("diogenes.mcp_server._create_search_provider")
    def test_search_error(self, mock_create: MagicMock) -> None:
        from diogenes.mcp_server import dio_search

        mock_provider = MagicMock()
        mock_provider.name = "serper"
        mock_provider.search.side_effect = RuntimeError("API error")
        mock_create.return_value = mock_provider

        reset_mcp_logger()
        result = json.loads(dio_search("test query"))
        assert result["error"] is True
        reset_mcp_logger()


class TestDioFetch:
    """Tests for dio_fetch tool."""

    def setup_method(self) -> None:
        reset_mcp_logger()
        reset_content_cache()

    def teardown_method(self) -> None:
        reset_mcp_logger()
        reset_content_cache()

    @patch("diogenes.mcp_server.fetch_page_extract")
    def test_fetch_success(self, mock_fetch: MagicMock) -> None:
        from diogenes.mcp_server import dio_fetch

        mock_fetch.return_value = "Article body content"
        result = json.loads(dio_fetch("https://example.com"))
        assert result["url"] == "https://example.com"
        assert result["content"] == "Article body content"
        assert result["content_length"] == 20

    @patch("diogenes.mcp_server.fetch_page_extract")
    def test_fetch_caches_content(self, mock_fetch: MagicMock) -> None:
        from diogenes.content_cache import get_content_cache
        from diogenes.mcp_server import dio_fetch

        mock_fetch.return_value = "cached body"
        dio_fetch("https://example.com")
        cache = get_content_cache()
        assert cache.get("https://example.com") == "cached body"

    @patch("diogenes.mcp_server.fetch_page_extract")
    def test_fetch_error(self, mock_fetch: MagicMock) -> None:
        from diogenes.mcp_server import dio_fetch
        from diogenes.search import FetchError

        mock_fetch.side_effect = FetchError("timeout")
        result = json.loads(dio_fetch("https://example.com"))
        assert result["error"] is True

    @patch("diogenes.mcp_server.fetch_page_extract")
    def test_fetch_error_pdf_kind(self, mock_fetch: MagicMock) -> None:
        from diogenes.events import get_mcp_logger
        from diogenes.mcp_server import dio_fetch
        from diogenes.search import FetchError

        mock_fetch.side_effect = FetchError("PDF parse error")
        dio_fetch("https://example.com/doc.pdf")
        logger = get_mcp_logger()
        assert any(e["kind"] == "fetch_failed_pdf" for e in logger.events)

    @patch("diogenes.mcp_server.fetch_page_extract")
    def test_fetch_error_html_kind(self, mock_fetch: MagicMock) -> None:
        from diogenes.events import get_mcp_logger
        from diogenes.mcp_server import dio_fetch
        from diogenes.search import FetchError

        mock_fetch.side_effect = FetchError("trafilatura returned nothing")
        dio_fetch("https://example.com")
        logger = get_mcp_logger()
        assert any(e["kind"] == "fetch_failed_html" for e in logger.events)


class TestDioSearchBatch:
    """Tests for dio_search_batch tool."""

    @patch("diogenes.mcp_server._create_search_provider")
    def test_batch_success(self, mock_create: MagicMock) -> None:
        from diogenes.mcp_server import dio_search_batch
        from diogenes.search import SearchResult

        mock_provider = MagicMock()
        mock_provider.name = "serper"
        mock_provider.search.return_value = ([SearchResult(title="T", url="u", snippet="s")], 1)
        mock_create.return_value = mock_provider

        result = json.loads(dio_search_batch(["q1", "q2"], 3))
        assert result["searches_executed"] == 2
        assert len(result["results"]) == 2

    @patch("diogenes.mcp_server._create_search_provider")
    def test_batch_partial_error(self, mock_create: MagicMock) -> None:
        from diogenes.mcp_server import dio_search_batch

        mock_provider = MagicMock()
        mock_provider.name = "serper"
        mock_provider.search.side_effect = [RuntimeError("fail"), ([], 0)]
        mock_create.return_value = mock_provider

        reset_mcp_logger()
        result = json.loads(dio_search_batch(["q1", "q2"]))
        assert len(result["results"]) == 2
        assert "error" in result["results"][0]
        reset_mcp_logger()


class TestDioFlushEvents:
    """Tests for dio_flush_events tool."""

    def setup_method(self) -> None:
        reset_mcp_logger()

    def teardown_method(self) -> None:
        reset_mcp_logger()

    def test_no_output_dir(self) -> None:
        from diogenes.mcp_server import dio_flush_events

        result = json.loads(dio_flush_events())
        assert result["error"] is True

    def test_flush_success(self, tmp_path: pytest.TempPathFactory) -> None:
        from diogenes.events import get_mcp_logger
        from diogenes.mcp_server import dio_flush_events

        logger = get_mcp_logger()
        logger.set_output_dir(tmp_path)  # type: ignore[arg-type]
        # Create minimal run files so reconciler doesn't fail
        for fname in ("search-results.json", "scorecards.json", "evidence-packets.json"):
            (tmp_path / fname).write_text("{}")  # type: ignore[operator]
        result = json.loads(dio_flush_events())
        assert "written_to" in result
        assert (tmp_path / "pipeline-events.json").exists()  # type: ignore[operator]


class TestDioValidatePackets:
    """Tests for dio_validate_packets tool."""

    def setup_method(self) -> None:
        reset_mcp_logger()
        reset_content_cache()

    def teardown_method(self) -> None:
        reset_mcp_logger()
        reset_content_cache()

    def test_missing_packets_file(self, tmp_path: pytest.TempPathFactory) -> None:
        from diogenes.mcp_server import dio_validate_packets

        result = json.loads(dio_validate_packets(str(tmp_path)))
        assert result["error"] is True

    def test_cli_format_validation(self, tmp_path: pytest.TempPathFactory) -> None:
        from diogenes.mcp_server import dio_validate_packets

        # Create packets and scorecards in CLI format
        packets = {
            "Q001": {
                "id": "Q001",
                "packets": [
                    {"excerpt": "this is verbatim text", "source_url": "https://a.com"},
                    {"excerpt": "fabricated quote", "source_url": "https://a.com"},
                ],
            }
        }
        scorecards = {
            "Q001": {
                "scorecards": [
                    {"url": "https://a.com", "content_extract": "this is verbatim text from the source"},
                ],
            }
        }
        (tmp_path / "evidence-packets.json").write_text(json.dumps(packets))  # type: ignore[operator]
        (tmp_path / "scorecards.json").write_text(json.dumps(scorecards))  # type: ignore[operator]

        result = json.loads(dio_validate_packets(str(tmp_path)))
        assert result["validated"] is True
        assert result["packets_kept"] == 1
        assert result["packets_dropped"] == 1

    def test_skill_format_validation(self, tmp_path: pytest.TempPathFactory) -> None:
        from diogenes.mcp_server import dio_validate_packets

        packets = {
            "id": "Q001",
            "packets": [
                {"excerpt": "real text here", "source_url": "https://a.com"},
            ],
        }
        scorecards = {
            "scorecards": [
                {"url": "https://a.com", "content_extract": "the real text here is good"},
            ],
        }
        (tmp_path / "evidence-packets.json").write_text(json.dumps(packets))  # type: ignore[operator]
        (tmp_path / "scorecards.json").write_text(json.dumps(scorecards))  # type: ignore[operator]

        result = json.loads(dio_validate_packets(str(tmp_path)))
        assert result["validated"] is True
        assert result["packets_kept"] == 1

    def test_non_dict_item_skipped(self, tmp_path: pytest.TempPathFactory) -> None:
        """Covers line 486: non-dict value in packets_data is skipped."""
        from diogenes.mcp_server import dio_validate_packets

        # CLI format with a non-dict value mixed in
        packets = {
            "Q001": {"id": "Q001", "packets": []},
            "metadata": "not a dict",
        }
        (tmp_path / "evidence-packets.json").write_text(json.dumps(packets))  # type: ignore[operator]
        (tmp_path / "scorecards.json").write_text("{}")  # type: ignore[operator]

        result = json.loads(dio_validate_packets(str(tmp_path)))
        assert result["validated"] is True
        assert result["packets_claimed"] == 0

    def test_cache_url_already_in_content(self, tmp_path: pytest.TempPathFactory) -> None:
        """Covers branch 468->467: cache URL already has content from scorecards."""
        from diogenes.content_cache import get_content_cache
        from diogenes.mcp_server import dio_validate_packets

        cache = get_content_cache()
        cache.put("https://a.com", "cached content that is not needed")

        # Scorecards already provide content for the same URL
        packets = {"Q001": {"id": "Q001", "packets": []}}
        scorecards = {
            "Q001": {
                "scorecards": [
                    {"url": "https://a.com", "content_extract": "scorecard content"},
                ],
            }
        }
        (tmp_path / "evidence-packets.json").write_text(json.dumps(packets))  # type: ignore[operator]
        (tmp_path / "scorecards.json").write_text(json.dumps(scorecards))  # type: ignore[operator]

        result = json.loads(dio_validate_packets(str(tmp_path)))
        assert result["validated"] is True

    def test_cache_url_returns_empty(self, tmp_path: pytest.TempPathFactory) -> None:
        """Covers branch 470->467: cache.get returns empty/None for a URL."""
        from diogenes.content_cache import get_content_cache
        from diogenes.mcp_server import dio_validate_packets

        cache = get_content_cache()
        cache.put("https://empty.com", "")

        packets = {"Q001": {"id": "Q001", "packets": []}}
        (tmp_path / "evidence-packets.json").write_text(json.dumps(packets))  # type: ignore[operator]
        (tmp_path / "scorecards.json").write_text("{}")  # type: ignore[operator]

        result = json.loads(dio_validate_packets(str(tmp_path)))
        assert result["validated"] is True

    def test_scorecard_skill_format_empty_url(self, tmp_path: pytest.TempPathFactory) -> None:
        """Covers branch 546->543: skill-format scorecard with empty url."""
        from diogenes.mcp_server import dio_validate_packets

        packets = {"id": "Q001", "packets": []}
        scorecards = {
            "scorecards": [
                {"url": "", "content_extract": "content"},
                {"url": "https://a.com", "content_extract": ""},
            ],
        }
        (tmp_path / "evidence-packets.json").write_text(json.dumps(packets))  # type: ignore[operator]
        (tmp_path / "scorecards.json").write_text(json.dumps(scorecards))  # type: ignore[operator]

        result = json.loads(dio_validate_packets(str(tmp_path)))
        assert result["validated"] is True

    def test_scorecard_cli_format_non_dict_values(self, tmp_path: pytest.TempPathFactory) -> None:
        """Covers branch 550->549: CLI-format scorecards with non-dict items."""
        from diogenes.mcp_server import dio_validate_packets

        packets = {"Q001": {"id": "Q001", "packets": []}}
        scorecards = {
            "Q001": {"scorecards": [{"url": "", "content_extract": "content"}]},
            "metadata": "string value",
        }
        (tmp_path / "evidence-packets.json").write_text(json.dumps(packets))  # type: ignore[operator]
        (tmp_path / "scorecards.json").write_text(json.dumps(scorecards))  # type: ignore[operator]

        result = json.loads(dio_validate_packets(str(tmp_path)))
        assert result["validated"] is True

    def test_uses_content_cache(self, tmp_path: pytest.TempPathFactory) -> None:
        from diogenes.content_cache import get_content_cache
        from diogenes.mcp_server import dio_validate_packets

        cache = get_content_cache()
        cache.put("https://a.com", "cached content matches exactly")

        packets = {
            "Q001": {
                "id": "Q001",
                "packets": [
                    {"excerpt": "cached content matches", "source_url": "https://a.com"},
                ],
            }
        }
        (tmp_path / "evidence-packets.json").write_text(json.dumps(packets))  # type: ignore[operator]
        (tmp_path / "scorecards.json").write_text("{}")  # type: ignore[operator]

        result = json.loads(dio_validate_packets(str(tmp_path)))
        assert result["packets_kept"] == 1


class TestDioRender:
    """Tests for dio_render tool."""

    def test_nonexistent_dir(self) -> None:
        from diogenes.mcp_server import dio_render

        result = json.loads(dio_render("/nonexistent", "/tmp/out"))
        assert result["error"] is True

    @patch("diogenes.mcp_server.render_run")
    def test_single_run(self, mock_render: MagicMock, tmp_path: pytest.TempPathFactory) -> None:
        from diogenes.mcp_server import dio_render

        run_dir = tmp_path / "run-1"  # type: ignore[operator]
        run_dir.mkdir()
        out_dir = tmp_path / "md"  # type: ignore[operator]

        result = json.loads(dio_render(str(run_dir), str(out_dir)))
        assert result["input_dir"] == str(run_dir)
        mock_render.assert_called_once()


class TestCreateSearchProvider:
    """Tests for _create_search_provider."""

    @patch("diogenes.mcp_server.load_config")
    def test_serper(self, mock_config: MagicMock) -> None:
        from diogenes.config import DioConfig
        from diogenes.mcp_server import _create_search_provider

        mock_config.return_value = DioConfig(api_key="key", serper_api_key="skey")
        provider = _create_search_provider()
        assert provider.name == "serper"

    @patch("diogenes.mcp_server.load_config")
    def test_brave(self, mock_config: MagicMock) -> None:
        from diogenes.config import DioConfig
        from diogenes.mcp_server import _create_search_provider

        mock_config.return_value = DioConfig(api_key="key", search_provider="brave", brave_api_key="bk")
        provider = _create_search_provider()
        assert provider.name == "brave"

    @patch("diogenes.mcp_server.load_config")
    def test_google(self, mock_config: MagicMock) -> None:
        from diogenes.config import DioConfig
        from diogenes.mcp_server import _create_search_provider

        mock_config.return_value = DioConfig(
            api_key="key", search_provider="google", google_api_key="gk", google_search_engine_id="cx"
        )
        provider = _create_search_provider()
        assert provider.name == "google"

    @patch("diogenes.mcp_server.load_config")
    def test_unconfigured_raises(self, mock_config: MagicMock) -> None:
        from diogenes.config import ConfigError, DioConfig
        from diogenes.mcp_server import _create_search_provider

        mock_config.return_value = DioConfig(api_key="key", search_provider="serper")
        with pytest.raises(ConfigError):
            _create_search_provider()
