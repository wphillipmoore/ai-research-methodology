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
    _logical_name,
    describe_valid_step_identifiers,
    resolve_step_identifier,
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


class TestLogicalName:
    """Tests for the _logical_name helper."""

    def test_strips_step_prefix(self) -> None:
        assert _logical_name("step_09_reports") == "reports"

    def test_strips_multi_token_suffix(self) -> None:
        assert _logical_name("step_06_evidence_packets") == "evidence_packets"

    def test_leaves_non_canonical_name_unchanged(self) -> None:
        """Strings without the step_NN_ shape pass through untouched."""
        assert _logical_name("ad_hoc") == "ad_hoc"
        assert _logical_name("plain") == "plain"


class TestDescribeValidStepIdentifiers:
    """Tests for describe_valid_step_identifiers."""

    def test_lists_all_steps_numbered(self) -> None:
        identifiers = describe_valid_step_identifiers()
        assert len(identifiers) == len(PIPELINE_STEPS)
        # First entry is "1 (...)"
        assert identifiers[0].startswith("1 (")
        # Report step is the 9th and uses the logical suffix
        assert "9 (reports)" in identifiers


class TestResolveStepIdentifier:
    """Tests for resolve_step_identifier."""

    def test_numeric_string(self) -> None:
        assert resolve_step_identifier("9") == "step_09_reports"

    def test_integer(self) -> None:
        assert resolve_step_identifier(9) == "step_09_reports"

    def test_canonical_name(self) -> None:
        assert resolve_step_identifier("step_09_reports") == "step_09_reports"

    def test_canonical_name_case_insensitive(self) -> None:
        assert resolve_step_identifier("STEP_09_REPORTS") == "step_09_reports"

    def test_logical_suffix(self) -> None:
        assert resolve_step_identifier("reports") == "step_09_reports"

    def test_logical_suffix_case_insensitive(self) -> None:
        assert resolve_step_identifier("Reports") == "step_09_reports"

    def test_multi_token_logical_suffix(self) -> None:
        assert resolve_step_identifier("evidence_packets") == "step_06_evidence_packets"

    def test_short_alias_report_singular(self) -> None:
        """'report' (singular) maps to the reports step."""
        assert resolve_step_identifier("report") == "step_09_reports"

    def test_short_alias_audit(self) -> None:
        assert resolve_step_identifier("audit") == "step_08_self_audit"

    def test_short_alias_score(self) -> None:
        assert resolve_step_identifier("score") == "step_05_scorecards"

    def test_unknown_string_raises_with_hint(self) -> None:
        with pytest.raises(ValueError, match=r"Unknown pipeline step"):
            resolve_step_identifier("totally-made-up")

    def test_error_lists_valid_options(self) -> None:
        """The error message names valid steps so the user can retry."""
        with pytest.raises(ValueError, match=r"Unknown pipeline step") as exc:
            resolve_step_identifier("bogus")
        # Mentions at least one of the canonical logical names
        assert "reports" in str(exc.value)

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match=r"empty"):
            resolve_step_identifier("")

    def test_whitespace_only_raises(self) -> None:
        with pytest.raises(ValueError, match=r"empty"):
            resolve_step_identifier("   ")

    def test_numeric_out_of_range_low(self) -> None:
        with pytest.raises(ValueError, match=r"out of range"):
            resolve_step_identifier(0)

    def test_numeric_out_of_range_high(self) -> None:
        with pytest.raises(ValueError, match=r"out of range"):
            resolve_step_identifier(99)

    def test_numeric_string_out_of_range(self) -> None:
        with pytest.raises(ValueError, match=r"out of range"):
            resolve_step_identifier("99")

    def test_non_string_non_int_type_raises(self) -> None:
        with pytest.raises(TypeError, match=r"int or str"):
            resolve_step_identifier(3.14)  # type: ignore[arg-type]

    def test_bool_is_rejected(self) -> None:
        """``True`` is an int subclass — reject it explicitly rather than resolving to step 1.

        Prevents a typo like ``from_step=True`` from silently succeeding.
        The boolean positional args here are the whole point of the
        test, so silence FBT003.
        """
        with pytest.raises(TypeError, match=r"int or str"):
            resolve_step_identifier(True)  # noqa: FBT003
        with pytest.raises(TypeError, match=r"int or str"):
            resolve_step_identifier(False)  # noqa: FBT003

    def test_whitespace_padded_numeric_is_parsed(self) -> None:
        """'  9  ' (padding) still resolves — user shells occasionally pad values."""
        assert resolve_step_identifier("  9  ") == "step_09_reports"


class TestMarkStepAndLaterIncomplete:
    """Tests for PipelineState.mark_step_and_later_incomplete."""

    def test_clears_target_and_later_steps(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        state = PipelineState(run_dir)
        # Mark all 11 steps complete
        for step in PIPELINE_STEPS:
            state.mark_complete(step.name, output_file=step.output_file)
        assert state.all_complete()

        cleared = state.mark_step_and_later_incomplete("step_09_reports")

        # step_09 through step_11 (the last three) should be cleared;
        # step_01..step_08 remain complete.
        assert cleared == [
            "step_09_reports",
            "step_10_archive",
            "step_11_pipeline_events",
        ]
        assert not state.is_complete("step_09_reports")
        assert not state.is_complete("step_10_archive")
        assert not state.is_complete("step_11_pipeline_events")
        assert state.is_complete("step_08_self_audit")
        assert state.is_complete("step_01_research_input_clarified")

    def test_clears_from_first_step_wipes_all(self, tmp_path: Path) -> None:
        """Clearing from step 1 resets every step."""
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        state = PipelineState(run_dir)
        for step in PIPELINE_STEPS:
            state.mark_complete(step.name)

        cleared = state.mark_step_and_later_incomplete(
            "step_01_research_input_clarified",
        )
        assert len(cleared) == len(PIPELINE_STEPS)
        assert not state.all_complete()
        # Every step now absent from _completed
        for step in PIPELINE_STEPS:
            assert not state.is_complete(step.name)

    def test_clears_step_that_was_not_previously_recorded(self, tmp_path: Path) -> None:
        """Clearing a step that hasn't been started is a no-op on that slot but still returns it."""
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        state = PipelineState(run_dir)
        # Only step_01 complete; later steps never recorded.
        state.mark_complete("step_01_research_input_clarified")

        cleared = state.mark_step_and_later_incomplete("step_05_scorecards")
        # Returned list is every step from 5 onward, regardless of prior presence.
        assert cleared[0] == "step_05_scorecards"
        assert "step_11_pipeline_events" in cleared
        # step_01 untouched
        assert state.is_complete("step_01_research_input_clarified")

    def test_persists_cleared_state_to_disk(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        state = PipelineState(run_dir)
        state.mark_complete("step_09_reports", output_file="reports.json")
        state.mark_step_and_later_incomplete("step_09_reports")

        # Reload from disk — the cleared record must not reappear.
        reloaded = PipelineState(run_dir)
        assert not reloaded.is_complete("step_09_reports")

    def test_unknown_step_raises(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        state = PipelineState(run_dir)
        with pytest.raises(ValueError, match=r"Unknown pipeline step"):
            state.mark_step_and_later_incomplete("not_a_real_step")
