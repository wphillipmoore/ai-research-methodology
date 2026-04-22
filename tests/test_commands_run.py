"""Tests for commands/run module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from diogenes.commands.run import (
    _create_run_group_dir,
    _create_search_provider,
    _dispatch_step,
    _parse_and_clarify,
    _timestamp,
    _write_research_input,
    execute,
)
from diogenes.events import EventLogger
from diogenes.state_machine import PIPELINE_STEPS, StepDefinition


class TestTimestamp:
    """Tests for _timestamp."""

    def test_format(self) -> None:
        ts = _timestamp()
        # Should be YYYY-MM-DD-HHMMSS
        assert len(ts) == 17
        assert ts[4] == "-"
        assert ts[7] == "-"
        assert ts[10] == "-"


class TestCreateRunGroupDir:
    """Tests for _create_run_group_dir."""

    def test_single_run(self, tmp_path: pytest.TempPathFactory) -> None:
        group_dir, run_dirs = _create_run_group_dir(tmp_path, 1)  # type: ignore[arg-type]
        assert group_dir.exists()
        assert len(run_dirs) == 1
        assert run_dirs[0].name == "run-1"

    def test_multiple_runs(self, tmp_path: pytest.TempPathFactory) -> None:
        group_dir, run_dirs = _create_run_group_dir(tmp_path, 3)  # type: ignore[arg-type]
        assert len(run_dirs) == 3
        assert run_dirs[0].name == "run-1"
        assert run_dirs[2].name == "run-3"

    def test_zero_padding(self, tmp_path: pytest.TempPathFactory) -> None:
        group_dir, run_dirs = _create_run_group_dir(tmp_path, 12)  # type: ignore[arg-type]
        assert run_dirs[0].name == "run-01"
        assert run_dirs[11].name == "run-12"


class TestWriteResearchInput:
    """Tests for _write_research_input."""

    def test_writes_file(self, tmp_path: pytest.TempPathFactory) -> None:
        data = {"claims": [], "queries": []}
        path = _write_research_input(tmp_path, data)  # type: ignore[arg-type]
        assert path.exists()
        assert json.loads(path.read_text()) == data

    def test_exits_if_exists(self, tmp_path: pytest.TempPathFactory) -> None:
        data = {"claims": []}
        # Pre-create the file
        (tmp_path / "research-input-clarified.json").write_text("{}")  # type: ignore[operator]
        with pytest.raises(SystemExit):
            _write_research_input(tmp_path, data)  # type: ignore[arg-type]


class TestParseAndClarify:
    """Tests for _parse_and_clarify."""

    def test_json_input(self, tmp_path: pytest.TempPathFactory) -> None:
        path = tmp_path / "input.json"  # type: ignore[operator]
        path.write_text(json.dumps({"claims": [{"text": "Test"}], "queries": []}))
        result = _parse_and_clarify(path, MagicMock())
        assert result is not None
        assert "claims" in result

    def test_json_invalid_schema(self, tmp_path: pytest.TempPathFactory) -> None:
        path = tmp_path / "input.json"  # type: ignore[operator]
        path.write_text(json.dumps({"bad": "schema"}))
        result = _parse_and_clarify(path, MagicMock())
        assert result is None

    def test_text_input(self, tmp_path: pytest.TempPathFactory) -> None:
        path = tmp_path / "input.md"  # type: ignore[operator]
        path.write_text("Is AI reliable?")

        mock_client = MagicMock()
        mock_client.call_sub_agent.return_value = {
            "claims": [],
            "queries": [{"text": "Is AI reliable?"}],
        }
        result = _parse_and_clarify(path, mock_client)
        assert result is not None
        assert "queries" in result

    def test_text_input_clarifier_error(self, tmp_path: pytest.TempPathFactory) -> None:
        path = tmp_path / "input.md"  # type: ignore[operator]
        path.write_text("bad input")

        mock_client = MagicMock()
        mock_client.call_sub_agent.return_value = {"error": True, "message": "could not parse"}
        result = _parse_and_clarify(path, mock_client)
        assert result is None

    def test_text_input_api_failure(self, tmp_path: pytest.TempPathFactory) -> None:
        from diogenes.api_client import SubAgentError

        path = tmp_path / "input.md"  # type: ignore[operator]
        path.write_text("test")

        mock_client = MagicMock()
        mock_client.call_sub_agent.side_effect = SubAgentError("clarifier", "API error")
        result = _parse_and_clarify(path, mock_client)
        assert result is None

    def test_missing_file(self) -> None:
        result = _parse_and_clarify(Path("/nonexistent/input.json"), MagicMock())
        assert result is None


class TestCreateSearchProvider:
    """Tests for _create_search_provider."""

    @patch("diogenes.commands.run.load_config")
    def test_serper(self, mock_config: MagicMock) -> None:
        from diogenes.config import DioConfig

        mock_config.return_value = DioConfig(api_key="key", serper_api_key="skey")
        provider = _create_search_provider()
        assert provider is not None
        assert provider.name == "serper"  # type: ignore[union-attr]

    @patch("diogenes.commands.run.load_config")
    def test_brave(self, mock_config: MagicMock) -> None:
        from diogenes.config import DioConfig

        mock_config.return_value = DioConfig(api_key="key", search_provider="brave", brave_api_key="bkey")
        provider = _create_search_provider()
        assert provider is not None
        assert provider.name == "brave"  # type: ignore[union-attr]

    @patch("diogenes.commands.run.load_config")
    def test_google(self, mock_config: MagicMock) -> None:
        from diogenes.config import DioConfig

        mock_config.return_value = DioConfig(
            api_key="key",
            search_provider="google",
            google_api_key="gkey",
            google_search_engine_id="gcx",
        )
        provider = _create_search_provider()
        assert provider is not None
        assert provider.name == "google"  # type: ignore[union-attr]

    @patch("diogenes.commands.run.load_config")
    def test_serper_missing_key(self, mock_config: MagicMock) -> None:
        from diogenes.config import DioConfig

        mock_config.return_value = DioConfig(api_key="key")
        provider = _create_search_provider()
        assert provider is None

    @patch("diogenes.commands.run.load_config")
    def test_brave_missing_key(self, mock_config: MagicMock) -> None:
        from diogenes.config import DioConfig

        mock_config.return_value = DioConfig(api_key="key", search_provider="brave")
        provider = _create_search_provider()
        assert provider is None

    @patch("diogenes.commands.run.load_config")
    def test_google_missing_key(self, mock_config: MagicMock) -> None:
        from diogenes.config import DioConfig

        mock_config.return_value = DioConfig(api_key="key", search_provider="google")
        provider = _create_search_provider()
        assert provider is None

    @patch("diogenes.commands.run.load_config")
    def test_unknown_provider(self, mock_config: MagicMock) -> None:
        from diogenes.config import DioConfig

        mock_config.return_value = DioConfig(api_key="key", search_provider="unknown")
        provider = _create_search_provider()
        assert provider is None


class TestDispatchStep:
    """Tests for _dispatch_step."""

    def _make_context(self, tmp_path: pytest.TempPathFactory) -> tuple:
        outputs = {"research_input": {"claims": [], "queries": []}}
        client = MagicMock()
        client.model = "test-model"
        search_provider = MagicMock()
        event_logger = EventLogger(run_id="test", output_dir=tmp_path)  # type: ignore[arg-type]
        run_dir = tmp_path  # type: ignore[assignment]
        return outputs, client, search_provider, event_logger, run_dir

    def test_step_01_returns_research_input(self, tmp_path: pytest.TempPathFactory) -> None:
        outputs, client, sp, el, rd = self._make_context(tmp_path)
        step = PIPELINE_STEPS[0]  # step_01
        result = _dispatch_step(step, outputs, client, sp, el, rd)
        assert result == outputs["research_input"]

    def test_step_02_calls_handler(self, tmp_path: pytest.TempPathFactory) -> None:
        outputs, client, sp, el, rd = self._make_context(tmp_path)
        client.call_sub_agent = MagicMock(return_value={"approach": "hypotheses", "hypotheses": []})
        step = PIPELINE_STEPS[1]  # step_02
        with patch("diogenes.commands.run.step2_generate_hypotheses", return_value={"Q001": {}}) as mock:
            result = _dispatch_step(step, outputs, client, sp, el, rd)
        mock.assert_called_once()

    def test_step_10_archive(self, tmp_path: pytest.TempPathFactory) -> None:
        outputs, client, sp, el, rd = self._make_context(tmp_path)
        step = PIPELINE_STEPS[9]  # step_10_archive
        with patch("diogenes.commands.run.step11_archive") as mock:
            result = _dispatch_step(step, outputs, client, sp, el, rd)
        assert result == {"_self_written": True}

    def test_step_11_events(self, tmp_path: pytest.TempPathFactory) -> None:
        outputs, client, sp, el, rd = self._make_context(tmp_path)
        step = PIPELINE_STEPS[10]  # step_11_pipeline_events
        with patch(
            "diogenes.commands.run.reconcile_run",
            return_value={"verbatim_adherence_pct": 75.0, "sources_scored": 10, "sources_attempted": 12},
        ):
            result = _dispatch_step(step, outputs, client, sp, el, rd)
        assert result == {"_self_written": True}

    def test_unknown_step(self, tmp_path: pytest.TempPathFactory) -> None:
        outputs, client, sp, el, rd = self._make_context(tmp_path)
        step = StepDefinition(name="unknown_step", display_name="Unknown", output_file="x.json", category="llm")
        result = _dispatch_step(step, outputs, client, sp, el, rd)
        assert result is None

    def test_step_03_calls_handler(self, tmp_path: pytest.TempPathFactory) -> None:
        outputs, client, sp, el, rd = self._make_context(tmp_path)
        outputs["hypotheses"] = {}
        step = PIPELINE_STEPS[2]  # step_03
        with patch("diogenes.commands.run.step3_design_searches", return_value={}) as mock:
            _dispatch_step(step, outputs, client, sp, el, rd)
        mock.assert_called_once()

    def test_step_04_calls_handler(self, tmp_path: pytest.TempPathFactory) -> None:
        outputs, client, sp, el, rd = self._make_context(tmp_path)
        outputs["search_plans"] = {}
        step = PIPELINE_STEPS[3]  # step_04
        with patch("diogenes.commands.run.step4_execute_searches", return_value={}) as mock:
            _dispatch_step(step, outputs, client, sp, el, rd)
        mock.assert_called_once()

    def test_step_05_calls_handler(self, tmp_path: pytest.TempPathFactory) -> None:
        outputs, client, sp, el, rd = self._make_context(tmp_path)
        outputs["search_results"] = {}
        step = PIPELINE_STEPS[4]  # step_05
        with patch("diogenes.commands.run.step5_score_sources", return_value={}) as mock:
            _dispatch_step(step, outputs, client, sp, el, rd)
        mock.assert_called_once()

    def test_step_06_calls_handler(self, tmp_path: pytest.TempPathFactory) -> None:
        outputs, client, sp, el, rd = self._make_context(tmp_path)
        outputs["hypotheses"] = {}
        outputs["scorecards"] = {}
        step = PIPELINE_STEPS[5]  # step_06
        with patch("diogenes.commands.run.step5b_extract_evidence", return_value={}) as mock:
            _dispatch_step(step, outputs, client, sp, el, rd)
        mock.assert_called_once()

    def test_step_07_calls_handler(self, tmp_path: pytest.TempPathFactory) -> None:
        outputs, client, sp, el, rd = self._make_context(tmp_path)
        outputs["hypotheses"] = {}
        outputs["scorecards"] = {}
        outputs["evidence_packets"] = {}
        step = PIPELINE_STEPS[6]  # step_07
        with patch("diogenes.commands.run.steps678_synthesize_and_assess", return_value={}) as mock:
            _dispatch_step(step, outputs, client, sp, el, rd)
        mock.assert_called_once()

    def test_step_08_calls_handler(self, tmp_path: pytest.TempPathFactory) -> None:
        outputs, client, sp, el, rd = self._make_context(tmp_path)
        outputs["hypotheses"] = {}
        outputs["search_results"] = {}
        outputs["scorecards"] = {}
        outputs["evidence_packets"] = {}
        outputs["synthesis"] = {}
        step = PIPELINE_STEPS[7]  # step_08
        with patch("diogenes.commands.run.step9_self_audit", return_value={}) as mock:
            _dispatch_step(step, outputs, client, sp, el, rd)
        mock.assert_called_once()

    def test_step_09_calls_handler(self, tmp_path: pytest.TempPathFactory) -> None:
        outputs, client, sp, el, rd = self._make_context(tmp_path)
        outputs["hypotheses"] = {}
        outputs["search_results"] = {}
        outputs["scorecards"] = {}
        outputs["synthesis"] = {}
        outputs["self_audit"] = {}
        step = PIPELINE_STEPS[8]  # step_09
        with patch("diogenes.commands.run.step10_report", return_value={}) as mock:
            _dispatch_step(step, outputs, client, sp, el, rd)
        mock.assert_called_once()

    def test_step_11_no_adherence(self, tmp_path: pytest.TempPathFactory) -> None:
        outputs, client, sp, el, rd = self._make_context(tmp_path)
        step = PIPELINE_STEPS[10]
        with patch(
            "diogenes.commands.run.reconcile_run",
            return_value={"verbatim_adherence_pct": None, "sources_scored": 0, "sources_attempted": 0},
        ):
            result = _dispatch_step(step, outputs, client, sp, el, rd)
        assert result == {"_self_written": True}

    def test_subagent_error_returns_none(self, tmp_path: pytest.TempPathFactory) -> None:
        from diogenes.api_client import SubAgentError

        outputs, client, sp, el, rd = self._make_context(tmp_path)
        step = PIPELINE_STEPS[1]  # step_02
        with patch("diogenes.commands.run.step2_generate_hypotheses", side_effect=SubAgentError("test", "error")):
            result = _dispatch_step(step, outputs, client, sp, el, rd)
        assert result is None


class TestExecute:
    """Tests for execute function."""

    @patch("diogenes.commands.run.APIClient")
    def test_api_client_failure(self, mock_cls: MagicMock) -> None:
        from diogenes.api_client import SubAgentError

        mock_cls.side_effect = SubAgentError("config", "No API key")
        assert execute("input.json", "/tmp/out", 1) == 1

    @patch("diogenes.commands.run._create_search_provider")
    @patch("diogenes.commands.run.APIClient")
    def test_search_provider_failure(self, mock_api: MagicMock, mock_sp: MagicMock) -> None:
        mock_sp.return_value = None
        assert execute("input.json", "/tmp/out", 1) == 1

    @patch("diogenes.commands.run._parse_and_clarify")
    @patch("diogenes.commands.run._create_search_provider")
    @patch("diogenes.commands.run.APIClient")
    def test_parse_failure(self, mock_api: MagicMock, mock_sp: MagicMock, mock_parse: MagicMock) -> None:
        mock_sp.return_value = MagicMock()
        mock_parse.return_value = None
        assert execute("input.json", "/tmp/out", 1) == 1
