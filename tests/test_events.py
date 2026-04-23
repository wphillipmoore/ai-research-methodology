"""Tests for events module."""

import json
from pathlib import Path

import pytest

from diogenes.events import EventLogger, _iter_items, _load_run_json, get_mcp_logger, reconcile_run, reset_mcp_logger


class TestEventLogger:
    """Tests for EventLogger."""

    def test_log_basic(self) -> None:
        logger = EventLogger(run_id="test-run")
        logger.log(step="step1", kind="error", detail="something broke", layer="pipeline")
        assert len(logger.events) == 1
        event = logger.events[0]
        assert event["step"] == "step1"
        assert event["kind"] == "error"
        assert event["detail"] == "something broke"
        assert event["layer"] == "pipeline"
        assert "timestamp" in event

    def test_log_with_optional_fields(self) -> None:
        logger = EventLogger(run_id="test-run")
        logger.log(
            step="step5",
            kind="fetch_failed",
            detail="timeout",
            layer="mcp",
            item_id="Q001",
            url="https://example.com",
            count=3,
            score=7.5,
            threshold=5.0,
        )
        event = logger.events[0]
        assert event["item_id"] == "Q001"
        assert event["url"] == "https://example.com"
        assert event["count"] == 3
        assert event["score"] == 7.5
        assert event["threshold"] == 5.0

    def test_events_returns_copy(self) -> None:
        logger = EventLogger(run_id="test-run")
        logger.log(step="s", kind="k", detail="d", layer="l")
        events = logger.events
        events.clear()
        assert len(logger.events) == 1

    def test_summary_empty(self) -> None:
        logger = EventLogger(run_id="test-run")
        s = logger.summary()
        assert s["total_events"] == 0
        assert s["by_kind"] == {}
        assert s["by_step"] == {}

    def test_summary_counts(self) -> None:
        logger = EventLogger(run_id="test-run")
        logger.log(step="step1", kind="error", detail="a", layer="l")
        logger.log(step="step1", kind="error", detail="b", layer="l")
        logger.log(step="step2", kind="warning", detail="c", layer="l")
        s = logger.summary()
        assert s["total_events"] == 3
        assert s["by_kind"] == {"error": 2, "warning": 1}
        assert s["by_step"] == {"step1": 2, "step2": 1}

    def test_summary_includes_coverage(self) -> None:
        logger = EventLogger(run_id="test-run")
        logger._coverage = {"sources_scored": 10}
        s = logger.summary()
        assert s["coverage"] == {"sources_scored": 10}

    def test_to_dict(self) -> None:
        logger = EventLogger(run_id="test-run", model="sonnet", execution_path="cli")
        logger.log(step="s", kind="k", detail="d", layer="l")
        d = logger.to_dict()
        assert d["run_id"] == "test-run"
        assert d["run_metadata"]["model"] == "sonnet"
        assert d["run_metadata"]["execution_path"] == "cli"
        assert len(d["events"]) == 1
        assert "summary" in d

    def test_write_to_path(self, tmp_path: Path) -> None:
        logger = EventLogger(run_id="test-run")
        logger.log(step="s", kind="k", detail="d", layer="l")
        path = tmp_path / "events.json"
        result = logger.write(path)
        assert result == path
        data = json.loads(path.read_text())
        assert data["run_id"] == "test-run"

    def test_write_to_output_dir(self, tmp_path: Path) -> None:
        logger = EventLogger(run_id="test-run", output_dir=tmp_path)
        logger.log(step="s", kind="k", detail="d", layer="l")
        result = logger.write()
        assert result == tmp_path / "pipeline-events.json"
        assert result.exists()

    def test_write_no_path_raises(self) -> None:
        logger = EventLogger(run_id="test-run")
        with pytest.raises(ValueError, match="No output directory"):
            logger.write()

    def test_set_output_dir(self, tmp_path: Path) -> None:
        logger = EventLogger(run_id="test-run")
        logger.set_output_dir(tmp_path)
        assert logger.output_dir == tmp_path


class TestLoadRunJson:
    """Tests for _load_run_json."""

    def test_valid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "data.json"
        path.write_text('{"key": "value"}')
        assert _load_run_json(path) == {"key": "value"}

    def test_missing_file(self, tmp_path: Path) -> None:
        path = tmp_path / "missing.json"
        assert _load_run_json(path) == {}

    def test_invalid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("not json")
        assert _load_run_json(path) == {}

    def test_non_dict_json(self, tmp_path: Path) -> None:
        path = tmp_path / "array.json"
        path.write_text("[1, 2, 3]")
        assert _load_run_json(path) == {}


class TestIterItems:
    """Tests for _iter_items."""

    def test_empty(self) -> None:
        assert _iter_items({}) == []

    def test_cli_format(self) -> None:
        data = {
            "Q001": {"id": "Q001", "packets": []},
            "C001": {"id": "C001", "packets": []},
        }
        items = _iter_items(data)
        assert len(items) == 2
        ids = {item_id for item_id, _ in items}
        assert ids == {"Q001", "C001"}

    def test_plugin_format(self) -> None:
        data = {"id": "Q001", "packets": []}
        items = _iter_items(data)
        assert len(items) == 1
        assert items[0][0] == "Q001"

    def test_ignores_non_dict_values(self) -> None:
        data = {"Q001": {"id": "Q001"}, "metadata": "string"}
        items = _iter_items(data)
        assert len(items) == 1


class TestReconcileRun:
    """Tests for reconcile_run."""

    def _create_run_dir(self, tmp_path: Path) -> pytest.TempPathFactory:
        """Create a minimal run directory with expected files."""
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()

        # Search results with selected sources
        search_results = {
            "Q001": {
                "id": "Q001",
                "selected_sources": [
                    {"url": "https://a.com"},
                    {"url": "https://b.com"},
                    {"url": "https://c.com"},
                ],
            }
        }
        (run_dir / "search-results.json").write_text(json.dumps(search_results))

        # Scorecards with 2 scored (1 fetch failure implied)
        scorecards = {
            "Q001": {
                "id": "Q001",
                "scorecards": [
                    {"url": "https://a.com", "score": 8},
                    {"url": "https://b.com", "score": 7},
                ],
            }
        }
        (run_dir / "scorecards.json").write_text(json.dumps(scorecards))

        # Evidence packets with verbatim stats
        evidence = {
            "Q001": {
                "id": "Q001",
                "packets": [],
                "verbatim_stats": {"claimed": 10, "kept": 7, "dropped": 3},
            }
        }
        (run_dir / "evidence-packets.json").write_text(json.dumps(evidence))

        # Create all expected step outputs
        for fname in (
            "hypotheses.json",
            "search-plans.json",
            "synthesis.json",
            "self-audit.json",
            "reports.json",
        ):
            (run_dir / fname).write_text("{}")

        return run_dir  # type: ignore[return-value]

    def test_basic_reconciliation(self, tmp_path: Path) -> None:
        run_dir = self._create_run_dir(tmp_path)
        logger = EventLogger(run_id="test")
        coverage = reconcile_run(run_dir, logger)  # type: ignore[arg-type]
        assert coverage["sources_selected"] == 3
        assert coverage["sources_scored"] == 2
        assert coverage["packets_claimed"] == 10
        assert coverage["packets_verified"] == 7
        assert coverage["packets_dropped"] == 3
        assert coverage["verbatim_adherence_pct"] == 70.0

    def test_missing_step_outputs(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-empty"
        run_dir.mkdir()
        for fname in ("search-results.json", "scorecards.json", "evidence-packets.json"):
            (run_dir / fname).write_text("{}")
        logger = EventLogger(run_id="test")
        reconcile_run(run_dir, logger)
        missing_events = [e for e in logger.events if e["kind"] == "missing_step_output"]
        assert len(missing_events) == 5  # hypotheses, search-plans, synthesis, self-audit, reports

    def test_zero_packets(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-zero"
        run_dir.mkdir()
        for fname in ("search-results.json", "scorecards.json", "evidence-packets.json"):
            (run_dir / fname).write_text("{}")
        logger = EventLogger(run_id="test")
        coverage = reconcile_run(run_dir, logger)
        assert coverage["packets_claimed"] == 0
        assert coverage["verbatim_adherence_pct"] is None

    def test_items_without_verbatim_stats(self, tmp_path: Path) -> None:
        """Covers the branch where item_data has no verbatim_stats (208->206)."""
        run_dir = tmp_path / "run-nostats"
        run_dir.mkdir()

        search_results = {
            "Q001": {
                "id": "Q001",
                "selected_sources": [{"url": "https://a.com"}],
            }
        }
        (run_dir / "search-results.json").write_text(json.dumps(search_results))

        scorecards = {"Q001": {"id": "Q001", "scorecards": [{"url": "https://a.com", "score": 8}]}}
        (run_dir / "scorecards.json").write_text(json.dumps(scorecards))

        # Evidence packets with NO verbatim_stats on the item
        evidence = {"Q001": {"id": "Q001", "packets": []}}
        (run_dir / "evidence-packets.json").write_text(json.dumps(evidence))

        for fname in ("hypotheses.json", "search-plans.json", "synthesis.json", "self-audit.json", "reports.json"):
            (run_dir / fname).write_text("{}")

        logger = EventLogger(run_id="test")
        coverage = reconcile_run(run_dir, logger)
        # With no verbatim_stats, packets_claimed should be 0
        assert coverage["packets_claimed"] == 0
        assert coverage["packets_verified"] == 0
        assert coverage["verbatim_adherence_pct"] is None

    def test_fetch_failures_counted(self, tmp_path: Path) -> None:
        run_dir = self._create_run_dir(tmp_path)
        logger = EventLogger(run_id="test")
        # Pre-log a fetch failure
        logger.log(step="step5", kind="fetch_failed", detail="timeout", layer="mcp", url="https://c.com")
        coverage = reconcile_run(run_dir, logger)  # type: ignore[arg-type]
        # 2 scored + 1 fetch failure = 3 attempted, matching 3 selected
        assert coverage["sources_attempted"] == 3
        assert coverage["sources_capped"] == 0

    def test_source_capping_logged(self, tmp_path: Path) -> None:
        run_dir = self._create_run_dir(tmp_path)
        logger = EventLogger(run_id="test")
        # No fetch failures logged, so attempted = scored = 2, but selected = 3
        # That means 1 was capped
        coverage = reconcile_run(run_dir, logger)  # type: ignore[arg-type]
        assert coverage["sources_capped"] == 1
        capped_events = [e for e in logger.events if e["kind"] == "source_capped"]
        assert len(capped_events) == 1


class TestMcpLoggerSingleton:
    """Tests for module-level MCP logger singleton."""

    def setup_method(self) -> None:
        reset_mcp_logger()

    def teardown_method(self) -> None:
        reset_mcp_logger()

    def test_get_creates_singleton(self) -> None:
        logger = get_mcp_logger()
        assert isinstance(logger, EventLogger)
        assert get_mcp_logger() is logger

    def test_reset_clears(self) -> None:
        logger = get_mcp_logger()
        reset_mcp_logger()
        new_logger = get_mcp_logger()
        assert new_logger is not logger

    def test_default_run_id(self) -> None:
        logger = get_mcp_logger()
        assert logger.run_id == "mcp-session"
