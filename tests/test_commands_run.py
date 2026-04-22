"""Tests for commands/run module."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from diogenes.commands.run import (
    _create_instance_dir,
    _create_search_provider,
    _dispatch_step,
    _find_saved_input,
    _load_prior_outputs,
    _parse_and_clarify,
    _timestamp,
    execute,
    execute_rerun,
    execute_resume,
)
from diogenes.events import EventLogger
from diogenes.state_machine import PIPELINE_STEPS, StepDefinition


class TestTimestamp:
    """Tests for _timestamp."""

    def test_format(self) -> None:
        ts = _timestamp()
        # YYYY-MM-DD-HHMMSS
        assert len(ts) == 17
        assert ts[4] == "-"
        assert ts[7] == "-"
        assert ts[10] == "-"


class TestCreateInstanceDir:
    """Tests for _create_instance_dir."""

    def test_creates_unique_dir(self, tmp_path: pytest.TempPathFactory) -> None:
        parent = tmp_path  # type: ignore[assignment]
        instance = _create_instance_dir(parent)  # type: ignore[arg-type]
        assert instance.exists()
        assert instance.parent == parent
        # Directory name is a timestamp
        assert len(instance.name) == 17

    def test_collision_retry(self, tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
        """If the first timestamp collides, sleep and retry with a later stamp."""
        # Pre-create a collision at the first timestamp we'll generate
        from diogenes.commands import run as run_mod

        ts1 = "2026-04-22-120000"
        ts2 = "2026-04-22-120001"
        (tmp_path / ts1).mkdir()  # type: ignore[operator]

        stamps = iter([ts1, ts2])
        monkeypatch.setattr(run_mod, "_timestamp", lambda: next(stamps))
        # Patch sleep so the test runs fast
        monkeypatch.setattr(run_mod.time, "sleep", lambda _s: None)

        instance = _create_instance_dir(tmp_path)  # type: ignore[arg-type]
        assert instance.name == ts2

    def test_exhausts_retries_raises(self, tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
        """If every retry hits a collision, raise RuntimeError."""
        from diogenes.commands import run as run_mod

        ts = "2026-04-22-120000"
        (tmp_path / ts).mkdir()  # type: ignore[operator]

        monkeypatch.setattr(run_mod, "_timestamp", lambda: ts)
        monkeypatch.setattr(run_mod.time, "sleep", lambda _s: None)

        with pytest.raises(RuntimeError, match="unique instance dir"):
            _create_instance_dir(tmp_path)  # type: ignore[arg-type]


class TestFindSavedInput:
    """Tests for _find_saved_input."""

    def test_single_file_found(self, tmp_path: pytest.TempPathFactory) -> None:
        (tmp_path / "input.md").write_text("content")  # type: ignore[operator]
        result = _find_saved_input(tmp_path)  # type: ignore[arg-type]
        assert result is not None
        assert result.name == "input.md"

    def test_ignores_subdirectories(self, tmp_path: pytest.TempPathFactory) -> None:
        (tmp_path / "input.md").write_text("content")  # type: ignore[operator]
        (tmp_path / "2026-04-22-120000").mkdir()  # type: ignore[operator]
        result = _find_saved_input(tmp_path)  # type: ignore[arg-type]
        assert result is not None
        assert result.name == "input.md"

    def test_ignores_hidden_files(self, tmp_path: pytest.TempPathFactory) -> None:
        (tmp_path / "input.md").write_text("content")  # type: ignore[operator]
        (tmp_path / ".DS_Store").write_text("")  # type: ignore[operator]
        result = _find_saved_input(tmp_path)  # type: ignore[arg-type]
        assert result is not None
        assert result.name == "input.md"

    def test_zero_candidates_returns_none(self, tmp_path: pytest.TempPathFactory) -> None:
        (tmp_path / "2026-04-22-120000").mkdir()  # type: ignore[operator]
        assert _find_saved_input(tmp_path) is None  # type: ignore[arg-type]

    def test_multiple_candidates_returns_none(self, tmp_path: pytest.TempPathFactory) -> None:
        (tmp_path / "a.md").write_text("content")  # type: ignore[operator]
        (tmp_path / "b.md").write_text("content")  # type: ignore[operator]
        assert _find_saved_input(tmp_path) is None  # type: ignore[arg-type]


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

    def test_step_11_events_with_events_logged(self, tmp_path: pytest.TempPathFactory) -> None:
        """Covers line 186: n_events is nonzero so the print fires."""
        outputs, client, sp, el, rd = self._make_context(tmp_path)
        # Add events to the logger so n_events > 0
        el.log(step="step5", kind="fetch_failed", detail="timeout", layer="pipeline")
        el.log(step="step5", kind="source_capped", detail="capped", layer="pipeline")
        step = PIPELINE_STEPS[10]  # step_11_pipeline_events
        with patch(
            "diogenes.commands.run.reconcile_run",
            return_value={"verbatim_adherence_pct": 80.0, "sources_scored": 5, "sources_attempted": 6},
        ):
            result = _dispatch_step(step, outputs, client, sp, el, rd)
        assert result == {"_self_written": True}

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
    def test_api_client_failure(self, mock_cls: MagicMock, tmp_path: pytest.TempPathFactory) -> None:
        from diogenes.api_client import SubAgentError

        mock_cls.side_effect = SubAgentError("config", "No API key")
        input_path = tmp_path / "input.json"  # type: ignore[operator]
        input_path.write_text(json.dumps({"claims": [], "queries": [{"text": "t"}]}))
        output_dir = tmp_path / "output"  # type: ignore[operator]
        assert execute(str(input_path), str(output_dir)) == 1

    @patch("diogenes.commands.run._create_search_provider")
    @patch("diogenes.commands.run.APIClient")
    def test_search_provider_failure(
        self,
        mock_api: MagicMock,
        mock_sp: MagicMock,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        mock_sp.return_value = None
        input_path = tmp_path / "input.json"  # type: ignore[operator]
        input_path.write_text(json.dumps({"claims": [], "queries": [{"text": "t"}]}))
        output_dir = tmp_path / "output"  # type: ignore[operator]
        assert execute(str(input_path), str(output_dir)) == 1

    def _make_input_file(self, tmp_path: Path, name: str = "input.json") -> Path:
        """Create a minimal valid JSON input file and return its path."""
        p = tmp_path / name
        p.write_text(json.dumps({"claims": [], "queries": [{"text": "test"}]}))
        return p

    def _usage_stub(self, *, with_web: bool = False) -> dict:
        return {
            "totals": {
                "api_calls": 1,
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
                "estimated_cost_usd": 0.0,
                "web_search_requests": 3 if with_web else 0,
                "web_fetch_requests": 2 if with_web else 0,
            },
            "per_call": [],
        }

    def test_missing_input_file(self, tmp_path: pytest.TempPathFactory) -> None:
        """Refuse to run if --input doesn't exist."""
        output_dir = tmp_path / "output"  # type: ignore[operator]
        result = execute("/nonexistent/input.md", str(output_dir))
        assert result == 1
        # Must not have created the output directory
        assert not output_dir.exists()

    def test_refuses_nonempty_output(self, tmp_path: pytest.TempPathFactory) -> None:
        """Refuses to silently reuse an existing research container."""
        output_dir = tmp_path / "output"  # type: ignore[operator]
        output_dir.mkdir()
        (output_dir / "existing.txt").write_text("leftover")
        input_path = self._make_input_file(tmp_path)  # type: ignore[arg-type]
        result = execute(str(input_path), str(output_dir))
        assert result == 1

    @patch("diogenes.commands.run._dispatch_step")
    @patch("diogenes.commands.run._parse_and_clarify")
    @patch("diogenes.commands.run._create_search_provider")
    @patch("diogenes.commands.run.APIClient")
    def test_full_pipeline_success(
        self,
        mock_api_cls: MagicMock,
        mock_sp: MagicMock,
        mock_parse: MagicMock,
        mock_dispatch: MagicMock,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """Happy path: run completes, creates instance dir, copies source, writes clarified in instance."""
        mock_client = MagicMock()
        mock_client.model = "test-model"
        mock_client.usage.to_dict.return_value = self._usage_stub(with_web=True)
        mock_api_cls.return_value = mock_client
        mock_sp.return_value = MagicMock()
        mock_parse.return_value = {"claims": [], "queries": [{"text": "test"}], "axioms": []}

        def dispatch_side_effect(step_def, outputs, client, sp, el, rd):
            if step_def.name in ("step_10_archive", "step_11_pipeline_events"):
                return {"_self_written": True}
            return {"result": "ok"}

        mock_dispatch.side_effect = dispatch_side_effect

        input_path = self._make_input_file(tmp_path, "input.md")  # type: ignore[arg-type]
        output_dir = tmp_path / "output"  # type: ignore[operator]
        result = execute(str(input_path), str(output_dir))
        assert result == 0

        # Source input copied to parent
        assert (output_dir / "input.md").exists()
        # Exactly one instance dir
        instance_dirs = [d for d in output_dir.iterdir() if d.is_dir()]
        assert len(instance_dirs) == 1
        # Clarified JSON lives INSIDE the instance dir (not at parent)
        assert (instance_dirs[0] / "research-input-clarified.json").exists()
        assert not (output_dir / "research-input-clarified.json").exists()
        # Dispatch called for steps 2-11 (step 1 is handled in _run_pipeline)
        assert mock_dispatch.call_count == 10

    @patch("diogenes.commands.run._dispatch_step")
    @patch("diogenes.commands.run._parse_and_clarify")
    @patch("diogenes.commands.run._create_search_provider")
    @patch("diogenes.commands.run.APIClient")
    def test_clarifier_failure(
        self,
        mock_api_cls: MagicMock,
        mock_sp: MagicMock,
        mock_parse: MagicMock,
        mock_dispatch: MagicMock,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """If _parse_and_clarify returns None, execute aborts with exit 1."""
        mock_api_cls.return_value = MagicMock(model="m")
        mock_sp.return_value = MagicMock()
        mock_parse.return_value = None

        input_path = self._make_input_file(tmp_path)  # type: ignore[arg-type]
        output_dir = tmp_path / "output"  # type: ignore[operator]
        result = execute(str(input_path), str(output_dir))
        assert result == 1

    @patch("diogenes.commands.run._dispatch_step")
    @patch("diogenes.commands.run._parse_and_clarify")
    @patch("diogenes.commands.run._create_search_provider")
    @patch("diogenes.commands.run.APIClient")
    def test_pipeline_step_failure(
        self,
        mock_api_cls: MagicMock,
        mock_sp: MagicMock,
        mock_parse: MagicMock,
        mock_dispatch: MagicMock,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """A dispatch failure causes execute to return 1."""
        mock_api_cls.return_value = MagicMock(model="m")
        mock_sp.return_value = MagicMock()
        mock_parse.return_value = {"claims": [], "queries": [], "axioms": []}
        mock_dispatch.return_value = None

        input_path = self._make_input_file(tmp_path)  # type: ignore[arg-type]
        output_dir = tmp_path / "output"  # type: ignore[operator]
        result = execute(str(input_path), str(output_dir))
        assert result == 1

    @patch("diogenes.commands.run._dispatch_step")
    @patch("diogenes.commands.run._parse_and_clarify")
    @patch("diogenes.commands.run._create_search_provider")
    @patch("diogenes.commands.run.APIClient")
    def test_pipeline_no_web_searches(
        self,
        mock_api_cls: MagicMock,
        mock_sp: MagicMock,
        mock_parse: MagicMock,
        mock_dispatch: MagicMock,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """Exercises the False branch of the web-search totals print."""
        mock_client = MagicMock(model="m")
        mock_client.usage.to_dict.return_value = self._usage_stub(with_web=False)
        mock_api_cls.return_value = mock_client
        mock_sp.return_value = MagicMock()
        mock_parse.return_value = {"claims": [], "queries": [], "axioms": []}

        def dispatch_side_effect(step_def, outputs, client, sp, el, rd):
            if step_def.name in ("step_10_archive", "step_11_pipeline_events"):
                return {"_self_written": True}
            return {"result": "ok"}

        mock_dispatch.side_effect = dispatch_side_effect

        input_path = self._make_input_file(tmp_path)  # type: ignore[arg-type]
        output_dir = tmp_path / "output"  # type: ignore[operator]
        result = execute(str(input_path), str(output_dir))
        assert result == 0

    @patch("diogenes.commands.run._dispatch_step")
    @patch("diogenes.commands.run._parse_and_clarify")
    @patch("diogenes.commands.run._create_search_provider")
    @patch("diogenes.commands.run.APIClient")
    def test_pipeline_does_not_write_prompt_snapshot(
        self,
        mock_api_cls: MagicMock,
        mock_sp: MagicMock,
        mock_parse: MagicMock,
        mock_dispatch: MagicMock,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """Regression guard: prompt-snapshot.md is never written.

        Replaced by the version block in pipeline-state.json (#127).
        """
        mock_client = MagicMock(model="m")
        mock_client.usage.to_dict.return_value = self._usage_stub()
        mock_api_cls.return_value = mock_client
        mock_sp.return_value = MagicMock()
        mock_parse.return_value = {"claims": [], "queries": [], "axioms": []}

        def dispatch_side_effect(step_def, outputs, client, sp, el, rd):
            if step_def.name in ("step_10_archive", "step_11_pipeline_events"):
                return {"_self_written": True}
            return {"result": "ok"}

        mock_dispatch.side_effect = dispatch_side_effect

        input_path = self._make_input_file(tmp_path)  # type: ignore[arg-type]
        output_dir = tmp_path / "output"  # type: ignore[operator]
        result = execute(str(input_path), str(output_dir))
        assert result == 0
        instance_dirs = [d for d in output_dir.iterdir() if d.is_dir()]
        assert len(instance_dirs) == 1
        assert not (instance_dirs[0] / "prompt-snapshot.md").exists()


class TestExecuteRerun:
    """Tests for execute_rerun."""

    def test_missing_output_dir(self) -> None:
        result = execute_rerun("/nonexistent/path")
        assert result == 1

    def test_missing_source_input(self, tmp_path: pytest.TempPathFactory) -> None:
        """If the parent has no saved source input, rerun aborts."""
        output_dir = tmp_path / "output"  # type: ignore[operator]
        output_dir.mkdir()
        # Only a subdirectory, no regular file
        (output_dir / "2026-04-22-120000").mkdir()

        result = execute_rerun(str(output_dir))
        assert result == 1

    @patch("diogenes.commands.run._dispatch_step")
    @patch("diogenes.commands.run._parse_and_clarify")
    @patch("diogenes.commands.run._create_search_provider")
    @patch("diogenes.commands.run.APIClient")
    def test_rerun_uses_saved_input(
        self,
        mock_api_cls: MagicMock,
        mock_sp: MagicMock,
        mock_parse: MagicMock,
        mock_dispatch: MagicMock,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """Rerun finds the saved input, runs a fresh instance, re-clarifies."""
        mock_client = MagicMock(model="m")
        mock_client.usage.to_dict.return_value = {
            "totals": {
                "api_calls": 1,
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
                "estimated_cost_usd": 0.0,
                "web_search_requests": 0,
                "web_fetch_requests": 0,
            },
            "per_call": [],
        }
        mock_api_cls.return_value = mock_client
        mock_sp.return_value = MagicMock()
        mock_parse.return_value = {"claims": [], "queries": [{"text": "t"}], "axioms": []}

        def dispatch_side_effect(step_def, outputs, client, sp, el, rd):
            if step_def.name in ("step_10_archive", "step_11_pipeline_events"):
                return {"_self_written": True}
            return {"result": "ok"}

        mock_dispatch.side_effect = dispatch_side_effect

        # Simulate a previous `dio run` having populated the parent.
        output_dir = tmp_path / "output"  # type: ignore[operator]
        output_dir.mkdir()
        saved_input = output_dir / "input.md"
        saved_input.write_text("previous research input")
        # Also simulate an existing prior instance
        (output_dir / "2026-04-22-100000").mkdir()

        result = execute_rerun(str(output_dir))
        assert result == 0

        # Rerun re-clarified (parse was called) — not a silent reuse.
        mock_parse.assert_called_once()

        # A new instance dir was created alongside the existing one.
        instance_dirs = sorted(d for d in output_dir.iterdir() if d.is_dir())
        assert len(instance_dirs) == 2
        # Each instance has its own clarified JSON
        new_instance = next(d for d in instance_dirs if d.name != "2026-04-22-100000")
        assert (new_instance / "research-input-clarified.json").exists()


def _seed_instance(
    instance_dir: Path,
    *,
    completed_step_files: dict[str, dict[str, Any]],
    running_step: str | None = None,
) -> None:
    """Seed a timestamped instance directory with prior step outputs + state.

    ``completed_step_files`` maps output_file names to the JSON content
    to write; each such step is marked ``complete`` in pipeline-state.json.
    ``running_step`` optionally marks one step as still in ``running``
    status to simulate an interrupted run.
    """
    from diogenes.state_machine import PIPELINE_STEPS, PipelineState

    instance_dir.mkdir(parents=True, exist_ok=True)
    for filename, payload in completed_step_files.items():
        (instance_dir / filename).write_text(json.dumps(payload))

    state = PipelineState(instance_dir)
    for step_def in PIPELINE_STEPS:
        if step_def.output_file and step_def.output_file in completed_step_files:
            state.mark_complete(step_def.name, output_file=step_def.output_file)
    if running_step:
        state.mark_started(running_step)


class TestLoadPriorOutputs:
    """Tests for _load_prior_outputs."""

    def test_loads_completed_outputs(self, tmp_path: pytest.TempPathFactory) -> None:
        """Each completed step's JSON is loaded under the pipeline's internal key."""
        from diogenes.state_machine import PipelineState

        instance_dir = tmp_path / "instance"  # type: ignore[operator]
        _seed_instance(
            instance_dir,
            completed_step_files={
                "research-input-clarified.json": {"claims": [], "queries": [{"text": "t"}]},
                "hypotheses.json": {"Q001": {"approach": "hypotheses"}},
            },
        )
        state = PipelineState(instance_dir)
        outputs = _load_prior_outputs(instance_dir, state)
        assert outputs is not None
        assert "research_input" in outputs
        assert "hypotheses" in outputs
        assert outputs["research_input"]["queries"][0]["text"] == "t"

    def test_skips_self_written_steps(self, tmp_path: pytest.TempPathFactory) -> None:
        """archive.json and pipeline-events.json are not hoisted into outputs."""
        from diogenes.state_machine import PipelineState

        instance_dir = tmp_path / "instance"  # type: ignore[operator]
        _seed_instance(
            instance_dir,
            completed_step_files={
                "research-input-clarified.json": {"claims": [], "queries": []},
                "archive.json": {"all": "steps"},
                "pipeline-events.json": {"events": []},
            },
        )
        state = PipelineState(instance_dir)
        outputs = _load_prior_outputs(instance_dir, state)
        assert outputs is not None
        assert "archive" not in outputs
        assert "pipeline_events" not in outputs

    def test_missing_output_file_is_inconsistent(self, tmp_path: pytest.TempPathFactory) -> None:
        """State says complete but file is gone → refuse to guess, return None."""
        from diogenes.state_machine import PipelineState

        instance_dir = tmp_path / "instance"  # type: ignore[operator]
        _seed_instance(
            instance_dir,
            completed_step_files={"research-input-clarified.json": {"claims": [], "queries": []}},
        )
        (instance_dir / "research-input-clarified.json").unlink()
        state = PipelineState(instance_dir)
        assert _load_prior_outputs(instance_dir, state) is None

    def test_skips_step_without_output_file(
        self,
        tmp_path: pytest.TempPathFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Defensive: a completed step with output_file=None is skipped, not a crash.

        PIPELINE_STEPS today has no such step, but StepDefinition permits it
        and this branch guards against a future step that mutates existing
        artifacts without creating a new file.
        """
        from diogenes.state_machine import PipelineState, StepDefinition

        fake_step = StepDefinition(
            name="step_fake_no_output",
            display_name="Fake",
            output_file=None,
            category="python_only",
        )
        monkeypatch.setattr("diogenes.commands.run.PIPELINE_STEPS", [fake_step])

        instance_dir = tmp_path / "instance"  # type: ignore[operator]
        instance_dir.mkdir()
        state = PipelineState(instance_dir)
        state.mark_complete("step_fake_no_output")

        # _load_prior_outputs walks the patched steps and must skip the
        # output_file=None step without erroring out.
        outputs = _load_prior_outputs(instance_dir, state)
        assert outputs == {}


class TestExecuteResume:
    """Tests for execute_resume."""

    def test_missing_instance_dir(self) -> None:
        assert execute_resume("/nonexistent/path") == 1

    def test_missing_state_file(self, tmp_path: pytest.TempPathFactory) -> None:
        """Instance dir exists but no pipeline-state.json → exit 1."""
        instance_dir = tmp_path / "instance"  # type: ignore[operator]
        instance_dir.mkdir()
        assert execute_resume(str(instance_dir)) == 1

    def test_all_steps_complete_is_noop(self, tmp_path: pytest.TempPathFactory) -> None:
        """Fully complete instance → exit 0 without dispatching anything."""
        from diogenes.state_machine import PIPELINE_STEPS, PipelineState

        instance_dir = tmp_path / "instance"  # type: ignore[operator]
        instance_dir.mkdir()
        state = PipelineState(instance_dir)
        for step_def in PIPELINE_STEPS:
            state.mark_complete(step_def.name, output_file=step_def.output_file)

        with patch("diogenes.commands.run._dispatch_step") as mock_dispatch:
            assert execute_resume(str(instance_dir)) == 0
            mock_dispatch.assert_not_called()

    def test_inconsistent_state_missing_output(self, tmp_path: pytest.TempPathFactory) -> None:
        """State says step complete but its output file is missing → exit 1."""
        instance_dir = tmp_path / "instance"  # type: ignore[operator]
        _seed_instance(
            instance_dir,
            completed_step_files={"research-input-clarified.json": {"claims": [], "queries": []}},
        )
        (instance_dir / "research-input-clarified.json").unlink()
        assert execute_resume(str(instance_dir)) == 1

    @patch("diogenes.commands.run.APIClient")
    def test_api_client_failure(self, mock_cls: MagicMock, tmp_path: pytest.TempPathFactory) -> None:
        from diogenes.api_client import SubAgentError

        mock_cls.side_effect = SubAgentError("config", "No API key")
        instance_dir = tmp_path / "instance"  # type: ignore[operator]
        _seed_instance(
            instance_dir,
            completed_step_files={"research-input-clarified.json": {"claims": [], "queries": []}},
        )
        assert execute_resume(str(instance_dir)) == 1

    @patch("diogenes.commands.run._create_search_provider")
    @patch("diogenes.commands.run.APIClient")
    def test_search_provider_failure(
        self,
        mock_api: MagicMock,
        mock_sp: MagicMock,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        mock_api.return_value = MagicMock(model="m")
        mock_sp.return_value = None
        instance_dir = tmp_path / "instance"  # type: ignore[operator]
        _seed_instance(
            instance_dir,
            completed_step_files={"research-input-clarified.json": {"claims": [], "queries": []}},
        )
        assert execute_resume(str(instance_dir)) == 1

    @patch("diogenes.commands.run._dispatch_step")
    @patch("diogenes.commands.run._parse_and_clarify")
    @patch("diogenes.commands.run._create_search_provider")
    @patch("diogenes.commands.run.APIClient")
    def test_resumes_from_first_incomplete_step(
        self,
        mock_api_cls: MagicMock,
        mock_sp: MagicMock,
        mock_parse: MagicMock,
        mock_dispatch: MagicMock,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """Completed steps are skipped; clarifier is NOT called (no re-parsing)."""
        mock_client = MagicMock(model="m")
        mock_client.usage.to_dict.return_value = {
            "totals": {
                "api_calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "estimated_cost_usd": 0.0,
                "web_search_requests": 0,
                "web_fetch_requests": 0,
            },
            "per_call": [],
        }
        mock_api_cls.return_value = mock_client
        mock_sp.return_value = MagicMock()

        def dispatch_side_effect(step_def, outputs, client, sp, el, rd):
            if step_def.name in ("step_10_archive", "step_11_pipeline_events"):
                return {"_self_written": True}
            return {"result": "ok"}

        mock_dispatch.side_effect = dispatch_side_effect

        # Seed: steps 1-3 complete on disk; 4-11 remain.
        instance_dir = tmp_path / "instance"  # type: ignore[operator]
        _seed_instance(
            instance_dir,
            completed_step_files={
                "research-input-clarified.json": {"claims": [], "queries": [{"text": "t"}], "axioms": []},
                "hypotheses.json": {"Q001": {"approach": "hypotheses"}},
                "search-plans.json": {"Q001": {"plan": "x"}},
            },
        )

        assert execute_resume(str(instance_dir)) == 0

        # Clarifier was NOT called — we read from disk instead.
        mock_parse.assert_not_called()

        # Dispatch fired only for the 8 remaining steps (step_04 through step_11).
        dispatched = [c.args[0].name for c in mock_dispatch.call_args_list]
        assert "step_02_hypotheses" not in dispatched
        assert "step_03_search_plans" not in dispatched
        assert dispatched[0] == "step_04_search_results"
        assert len(dispatched) == 8

    @patch("diogenes.commands.run._dispatch_step")
    @patch("diogenes.commands.run._create_search_provider")
    @patch("diogenes.commands.run.APIClient")
    def test_retries_running_step(
        self,
        mock_api_cls: MagicMock,
        mock_sp: MagicMock,
        mock_dispatch: MagicMock,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """A step left in 'running' status (interrupted) is re-executed."""
        mock_client = MagicMock(model="m")
        mock_client.usage.to_dict.return_value = {
            "totals": {
                "api_calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "estimated_cost_usd": 0.0,
                "web_search_requests": 0,
                "web_fetch_requests": 0,
            },
            "per_call": [],
        }
        mock_api_cls.return_value = mock_client
        mock_sp.return_value = MagicMock()

        def dispatch_side_effect(step_def, outputs, client, sp, el, rd):
            if step_def.name in ("step_10_archive", "step_11_pipeline_events"):
                return {"_self_written": True}
            return {"result": "ok"}

        mock_dispatch.side_effect = dispatch_side_effect

        instance_dir = tmp_path / "instance"  # type: ignore[operator]
        _seed_instance(
            instance_dir,
            completed_step_files={
                "research-input-clarified.json": {"claims": [], "queries": [], "axioms": []},
                "hypotheses.json": {"Q001": {}},
            },
            running_step="step_03_search_plans",
        )

        assert execute_resume(str(instance_dir)) == 0

        # The interrupted step is the first one re-dispatched.
        dispatched = [c.args[0].name for c in mock_dispatch.call_args_list]
        assert dispatched[0] == "step_03_search_plans"
