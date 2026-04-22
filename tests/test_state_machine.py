"""Tests for state_machine module."""

import json
import subprocess
from pathlib import Path

import pytest

from diogenes.state_machine import (
    PIPELINE_STEPS,
    PipelineState,
    StepDefinition,
    StepStatus,
    _compute_version,
    _git_metadata,
)


class TestStepDefinition:
    """Tests for StepDefinition dataclass."""

    def test_basic_creation(self) -> None:
        step = StepDefinition(
            name="test_step",
            display_name="Test Step",
            output_file="test.json",
            category="llm",
        )
        assert step.name == "test_step"
        assert step.display_name == "Test Step"
        assert step.output_file == "test.json"
        assert step.category == "llm"
        assert step.requires == []
        assert step.schema is None
        assert step.prompt is None
        assert step.python_handler is None
        assert step.post_validators == []
        assert step.mcp_tools == []
        assert step.per_source is False

    def test_full_creation(self) -> None:
        step = StepDefinition(
            name="step_05",
            display_name="Step 5",
            output_file="scorecards.json",
            category="hybrid",
            requires=["research-input.json"],
            schema="scorecards.schema.json",
            prompt="scorecards.md",
            python_handler="step5_score_sources",
            post_validators=["validate_packets"],
            mcp_tools=["dio_fetch"],
            per_source=True,
        )
        assert step.requires == ["research-input.json"]
        assert step.per_source is True


class TestPipelineSteps:
    """Tests for the canonical PIPELINE_STEPS list."""

    def test_has_11_steps(self) -> None:
        assert len(PIPELINE_STEPS) == 11

    def test_all_have_unique_names(self) -> None:
        names = [s.name for s in PIPELINE_STEPS]
        assert len(names) == len(set(names))

    def test_step_names_are_numbered(self) -> None:
        for i, step in enumerate(PIPELINE_STEPS, 1):
            assert step.name.startswith(f"step_{i:02d}_"), f"Step {i} name mismatch: {step.name}"

    def test_all_have_display_names(self) -> None:
        for step in PIPELINE_STEPS:
            assert step.display_name, f"{step.name} missing display_name"

    def test_all_have_categories(self) -> None:
        valid_categories = {"llm", "python_only", "hybrid"}
        for step in PIPELINE_STEPS:
            assert step.category in valid_categories, f"{step.name} has invalid category: {step.category}"


class TestStepStatus:
    """Tests for StepStatus dataclass."""

    def test_creation(self) -> None:
        status = StepStatus(name="step_01", status="complete")
        assert status.name == "step_01"
        assert status.status == "complete"
        assert status.started_at is None
        assert status.completed_at is None
        assert status.elapsed_seconds is None


class TestPipelineState:
    """Tests for PipelineState."""

    def test_fresh_state(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        state = PipelineState(run_dir)
        assert not state.all_complete()
        first = state.next_step()
        assert first is not None
        assert first.name == "step_01_research_input_clarified"

    def test_mark_complete(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        state = PipelineState(run_dir)
        state.mark_complete("step_01_research_input_clarified", output_file="research-input-clarified.json")
        assert state.is_complete("step_01_research_input_clarified")
        # State file should exist
        assert (run_dir / "pipeline-state.json").exists()

    def test_mark_started(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        state = PipelineState(run_dir)
        state.mark_started("step_01_research_input_clarified")
        assert not state.is_complete("step_01_research_input_clarified")
        data = json.loads((run_dir / "pipeline-state.json").read_text())
        assert data["steps"][0]["status"] == "running"

    def test_mark_failed(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        state = PipelineState(run_dir)
        state.mark_started("step_01_research_input_clarified")
        state.mark_failed("step_01_research_input_clarified", diagnostics="API error")
        assert not state.is_complete("step_01_research_input_clarified")
        data = json.loads((run_dir / "pipeline-state.json").read_text())
        assert data["steps"][0]["status"] == "failed"
        assert data["steps"][0]["diagnostics"] == "API error"

    def test_persistence_and_reload(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        state1 = PipelineState(run_dir)
        state1.mark_complete("step_01_research_input_clarified")
        # Reload from disk
        state2 = PipelineState(run_dir)
        assert state2.is_complete("step_01_research_input_clarified")

    def test_next_step_checks_prerequisites(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        state = PipelineState(run_dir)
        # Complete step 1
        state.mark_complete("step_01_research_input_clarified", output_file="research-input-clarified.json")
        # Step 2 requires research-input-clarified.json
        # File doesn't exist yet, so next_step should still be step 2
        # but prerequisites check against files on disk
        (run_dir / "research-input-clarified.json").write_text("{}")
        next_step = state.next_step()
        assert next_step is not None
        assert next_step.name == "step_02_hypotheses"

    def test_all_complete(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        state = PipelineState(run_dir)
        for step in PIPELINE_STEPS:
            state.mark_complete(step.name)
        assert state.all_complete()
        assert state.next_step() is None

    def test_summary(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        state = PipelineState(run_dir)
        state.mark_complete("step_01_research_input_clarified")
        s = state.summary()
        assert s["total_steps"] == 11
        assert s["completed"] == 1
        assert s["failed"] == 0
        assert s["remaining"] == 10

    def test_summary_with_failure(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        state = PipelineState(run_dir)
        state.mark_failed("step_01_research_input_clarified", diagnostics="err")
        s = state.summary()
        assert s["failed"] == 1
        assert s["remaining"] == 10

    def test_elapsed_seconds_computed(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        state = PipelineState(run_dir)
        state.mark_started("step_01_research_input_clarified")
        state.mark_complete("step_01_research_input_clarified")
        data = json.loads((run_dir / "pipeline-state.json").read_text())
        assert data["elapsed_seconds"] is not None
        assert data["elapsed_seconds"] >= 0

    def test_pid_captured_on_save(self, tmp_path: Path) -> None:
        """pipeline-state.json includes the PID of the writing process.

        Used to correlate OS-level crash reports (e.g., macOS SIGABRT)
        with a specific research run. Captured on every save so the value
        always reflects the currently-executing process.
        """
        import os

        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        state = PipelineState(run_dir)
        state.mark_complete("step_01_research_input_clarified")
        data = json.loads((run_dir / "pipeline-state.json").read_text())
        assert data["pid"] == os.getpid()

    def test_completed_at_set_when_all_done(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        state = PipelineState(run_dir)
        for step in PIPELINE_STEPS:
            state.mark_complete(step.name)
        data = json.loads((run_dir / "pipeline-state.json").read_text())
        assert data["completed_at"] is not None

    def test_mark_complete_without_prior_start(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        state = PipelineState(run_dir)
        # Complete without calling mark_started first
        state.mark_complete("step_01_research_input_clarified")
        assert state.is_complete("step_01_research_input_clarified")

    def test_mark_failed_without_prior_start(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        state = PipelineState(run_dir)
        state.mark_failed("step_01_research_input_clarified", diagnostics="immediate fail")
        data = json.loads((run_dir / "pipeline-state.json").read_text())
        assert data["steps"][0]["status"] == "failed"

    def test_save_with_invalid_created_at(self, tmp_path: Path) -> None:
        """Covers the ValueError handler in _save when _created_at is unparseable."""
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        state = PipelineState(run_dir)
        # Inject an invalid created_at to trigger the ValueError branch
        state._created_at = "not-a-timestamp"
        state.mark_complete("step_01_research_input_clarified")
        data = json.loads((run_dir / "pipeline-state.json").read_text())
        # elapsed_seconds should be None because parsing created_at failed
        assert data["elapsed_seconds"] is None

    def test_mark_complete_with_invalid_started_at(self, tmp_path: Path) -> None:
        """Covers the ValueError handler in mark_complete when started_at is unparseable."""
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        state = PipelineState(run_dir)
        # Inject a step with an invalid started_at
        state._completed["step_01_research_input_clarified"] = StepStatus(
            name="step_01_research_input_clarified",
            status="running",
            started_at="bad-timestamp",
        )
        state.mark_complete("step_01_research_input_clarified")
        data = json.loads((run_dir / "pipeline-state.json").read_text())
        step = data["steps"][0]
        assert step["status"] == "complete"
        assert step["elapsed_seconds"] is None

    def test_mark_failed_with_invalid_started_at(self, tmp_path: Path) -> None:
        """Covers the ValueError handler in mark_failed when started_at is unparseable."""
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        state = PipelineState(run_dir)
        # Inject a step with an invalid started_at
        state._completed["step_01_research_input_clarified"] = StepStatus(
            name="step_01_research_input_clarified",
            status="running",
            started_at="bad-timestamp",
        )
        state.mark_failed("step_01_research_input_clarified", diagnostics="err")
        data = json.loads((run_dir / "pipeline-state.json").read_text())
        step = data["steps"][0]
        assert step["status"] == "failed"
        assert step["elapsed_seconds"] is None

    def test_save_with_no_created_at(self, tmp_path: Path) -> None:
        """Covers 257->263: _save when _created_at is None (falsy)."""
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        # Pre-populate a state file with no created_at key
        (run_dir / "pipeline-state.json").write_text(json.dumps({"steps": []}))
        state = PipelineState(run_dir)
        state.mark_complete("step_01_research_input_clarified")
        data = json.loads((run_dir / "pipeline-state.json").read_text())
        # elapsed_seconds should be None because created_at is None
        assert data["elapsed_seconds"] is None

    def test_mark_complete_with_none_started_at(self, tmp_path: Path) -> None:
        """Covers 310->316: mark_complete when existing.started_at is None (falsy)."""
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        state = PipelineState(run_dir)
        # Inject a step with started_at=None
        state._completed["step_01_research_input_clarified"] = StepStatus(
            name="step_01_research_input_clarified",
            status="running",
            started_at=None,
        )
        state.mark_complete("step_01_research_input_clarified")
        data = json.loads((run_dir / "pipeline-state.json").read_text())
        step = data["steps"][0]
        assert step["status"] == "complete"
        assert step["elapsed_seconds"] is None

    def test_mark_failed_with_none_started_at(self, tmp_path: Path) -> None:
        """Covers 334->340: mark_failed when existing.started_at is None (falsy)."""
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        state = PipelineState(run_dir)
        state._completed["step_01_research_input_clarified"] = StepStatus(
            name="step_01_research_input_clarified",
            status="running",
            started_at=None,
        )
        state.mark_failed("step_01_research_input_clarified", diagnostics="err")
        data = json.loads((run_dir / "pipeline-state.json").read_text())
        step = data["steps"][0]
        assert step["status"] == "failed"
        assert step["elapsed_seconds"] is None


class TestGitMetadata:
    """Tests for _git_metadata helper."""

    def test_returns_dict_in_git_checkout(self) -> None:
        """Return real commit/branch/dirty when run inside the source checkout."""
        meta = _git_metadata()
        assert meta is not None
        assert isinstance(meta["commit"], str)
        # Commit is 40-char SHA
        assert len(meta["commit"]) == 40
        assert isinstance(meta["branch"], str)
        assert isinstance(meta["dirty"], bool)

    def test_returns_none_when_git_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """If the git CLI is missing (e.g., installed from a wheel), fall back cleanly."""

        def boom(*_args: object, **_kwargs: object) -> None:
            raise FileNotFoundError

        monkeypatch.setattr("diogenes.state_machine.subprocess.check_output", boom)
        assert _git_metadata() is None

    def test_returns_none_when_git_exits_nonzero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """If git returns non-zero (e.g., run outside a repo), fall back cleanly."""

        def boom(*_args: object, **_kwargs: object) -> None:
            raise subprocess.CalledProcessError(128, "git")

        monkeypatch.setattr("diogenes.state_machine.subprocess.check_output", boom)
        assert _git_metadata() is None


class TestComputeVersion:
    """Tests for _compute_version."""

    def test_always_includes_package_version(self) -> None:
        version = _compute_version()
        assert "package_version" in version

    def test_includes_git_fields_when_available(self) -> None:
        version = _compute_version()
        # When run in the source checkout (normal test environment), git fields
        # are present
        assert "git_commit" in version
        assert "git_branch" in version
        assert "git_dirty" in version

    def test_omits_git_fields_when_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("diogenes.state_machine._git_metadata", lambda: None)
        version = _compute_version()
        assert set(version.keys()) == {"package_version"}


class TestVersionInPipelineState:
    """Version metadata persisted in pipeline-state.json."""

    def test_version_written_on_fresh_state(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        state = PipelineState(run_dir)
        state.mark_complete("step_01_research_input_clarified")
        data = json.loads((run_dir / "pipeline-state.json").read_text())
        assert "version" in data
        assert "package_version" in data["version"]

    def test_version_preserved_across_reload(self, tmp_path: Path) -> None:
        """Resuming a run keeps the version from when the run was created.

        The version stamp identifies which code produced the outputs, not
        which process most recently touched the state. Preserving it on
        reload means resuming on a different commit doesn't overwrite the
        provenance trail.
        """
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        # Pre-populate with a specific version block that differs from
        # whatever _compute_version would produce here
        preload = {
            "created_at": "2026-01-01T00:00:00Z",
            "version": {"package_version": "0.0.1-pinned", "git_commit": "abc123"},
            "steps": [],
        }
        (run_dir / "pipeline-state.json").write_text(json.dumps(preload))

        state = PipelineState(run_dir)
        state.mark_complete("step_01_research_input_clarified")
        data = json.loads((run_dir / "pipeline-state.json").read_text())
        assert data["version"]["package_version"] == "0.0.1-pinned"
        assert data["version"]["git_commit"] == "abc123"
