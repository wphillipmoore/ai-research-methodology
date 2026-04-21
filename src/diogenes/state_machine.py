"""Pipeline state machine for dual-execution-path orchestration.

Defines the research pipeline as a sequence of steps, each with:
- An output file (the artifact this step produces)
- Prerequisites (files that must exist before this step runs)
- A compiled sub-agent prompt (for LLM steps) or a Python handler name
- Post-step validators (run after the step completes)
- Required MCP tools (for skill-path execution)

Both CLI and skill paths read from the same step definitions. They
diverge only at the execution layer:
- CLI: calls Python handler functions directly
- Skill: agent calls dio_next_step() to get instructions, then either
  executes the LLM prompt or calls dio_execute_step() for Python-only work

The output directory IS the primary state store. pipeline-state.json
provides explicit step-completion tracking with timestamps and diagnostics.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path  # noqa: TC003 — needed at runtime for file operations
from typing import Any


@dataclass
class StepDefinition:
    """A single pipeline step in the research workflow."""

    name: str
    """Unique step identifier (e.g., 'step5b_extract_evidence')."""

    display_name: str
    """Human-readable name for progress output (e.g., 'Extracting evidence packets')."""

    output_file: str | None
    """The JSON file this step produces (e.g., 'evidence-packets.json'). None for steps
    that modify existing files rather than creating new ones."""

    category: str
    """One of 'llm', 'python_only', or 'hybrid'. Determines execution path."""

    requires: list[str] = field(default_factory=list)
    """Files that must exist before this step can run."""

    schema: str | None = None
    """Output schema filename (e.g., 'evidence-packets.schema.json'). Used for both
    constrained decoding (CLI) and post-hoc validation (skill)."""

    prompt: str | None = None
    """Compiled sub-agent prompt filename (e.g., 'evidence-packets.md'). None for
    Python-only steps."""

    python_handler: str | None = None
    """Name of the pipeline.py function to call for this step. Used by CLI path
    and by dio_execute_step for Python-only steps on the skill path."""

    post_validators: list[str] = field(default_factory=list)
    """Validator names to run after step completion (e.g., 'validate_packets')."""

    mcp_tools: list[str] = field(default_factory=list)
    """MCP tools the agent needs for this step (e.g., ['dio_fetch'])."""

    per_source: bool = False
    """If True, this step runs once per source (e.g., evidence extraction).
    The state machine handles iteration; the step function handles one source."""


# The canonical pipeline step sequence. Both CLI and skill paths use this.
# Order matters — each step's requires are checked against prior outputs.
PIPELINE_STEPS: list[StepDefinition] = [
    StepDefinition(
        name="step_01_research_input_clarified",
        display_name="Step 1: Clarifying input",
        output_file="research-input-clarified.json",
        category="llm",
        requires=[],
        schema="research-input-clarified.schema.json",
        prompt="research-input-clarified.md",
        python_handler="step2_generate_hypotheses",  # Legacy name — will rename in #117
    ),
    StepDefinition(
        name="step_02_hypotheses",
        display_name="Step 2: Generating competing hypotheses",
        output_file="hypotheses.json",
        category="llm",
        requires=["research-input-clarified.json"],
        schema="hypotheses.schema.json",
        prompt="hypotheses.md",
        python_handler="step2_generate_hypotheses",
    ),
    StepDefinition(
        name="step_03_search_plans",
        display_name="Step 3: Designing searches",
        output_file="search-plans.json",
        category="llm",
        requires=["research-input-clarified.json", "hypotheses.json"],
        schema="search-plans.schema.json",
        prompt="search-plans.md",
        python_handler="step3_design_searches",
    ),
    StepDefinition(
        name="step_04_search_results",
        display_name="Step 4: Executing searches",
        output_file="search-results.json",
        category="hybrid",
        requires=["research-input-clarified.json", "search-plans.json"],
        schema="search-results.schema.json",
        prompt="search-results.md",
        python_handler="step4_execute_searches",
        mcp_tools=["dio_search", "dio_search_batch"],
    ),
    StepDefinition(
        name="step_05_scorecards",
        display_name="Step 5: Scoring sources",
        output_file="scorecards.json",
        category="hybrid",
        requires=["research-input-clarified.json", "search-results.json"],
        schema="scorecards.schema.json",
        prompt="scorecards.md",
        python_handler="step5_score_sources",
        mcp_tools=["dio_fetch"],
    ),
    StepDefinition(
        name="step_06_evidence_packets",
        display_name="Step 6: Extracting evidence packets",
        output_file="evidence-packets.json",
        category="hybrid",
        requires=["research-input-clarified.json", "hypotheses.json", "scorecards.json"],
        schema="evidence-packets.schema.json",
        prompt="evidence-packets.md",
        python_handler="step5b_extract_evidence",
        post_validators=["validate_packets"],
        per_source=True,
    ),
    StepDefinition(
        name="step_07_synthesis",
        display_name="Step 7: Synthesizing evidence and assessing",
        output_file="synthesis.json",
        category="llm",
        requires=[
            "research-input-clarified.json",
            "hypotheses.json",
            "scorecards.json",
            "evidence-packets.json",
        ],
        schema="synthesis.schema.json",
        prompt="synthesis.md",
        python_handler="steps678_synthesize_and_assess",
    ),
    StepDefinition(
        name="step_08_self_audit",
        display_name="Step 8: Self-audit and verification",
        output_file="self-audit.json",
        category="llm",
        requires=[
            "research-input-clarified.json",
            "hypotheses.json",
            "search-results.json",
            "scorecards.json",
            "evidence-packets.json",
            "synthesis.json",
        ],
        schema="self-audit.schema.json",
        prompt="self-audit.md",
        python_handler="step9_self_audit",
    ),
    StepDefinition(
        name="step_09_reports",
        display_name="Step 9: Assembling final reports",
        output_file="reports.json",
        category="llm",
        requires=[
            "research-input-clarified.json",
            "hypotheses.json",
            "search-results.json",
            "scorecards.json",
            "synthesis.json",
            "self-audit.json",
        ],
        schema="reports.schema.json",
        prompt="reports.md",
        python_handler="step10_report",
    ),
    StepDefinition(
        name="step_10_archive",
        display_name="Step 10: Archiving",
        output_file="archive.json",
        category="python_only",
        requires=[
            "research-input-clarified.json",
            "hypotheses.json",
            "search-plans.json",
            "search-results.json",
            "scorecards.json",
            "evidence-packets.json",
            "synthesis.json",
            "self-audit.json",
            "reports.json",
        ],
        python_handler="step11_archive",
    ),
    StepDefinition(
        name="step_11_pipeline_events",
        display_name="Step 11: Reconciling events",
        output_file="pipeline-events.json",
        category="python_only",
        requires=["archive.json"],
        python_handler="reconcile_and_flush",
    ),
]


@dataclass
class StepStatus:
    """Completion record for a single step."""

    name: str
    status: str  # "running", "complete", "failed", "skipped"
    started_at: str | None = None
    completed_at: str | None = None
    elapsed_seconds: float | None = None
    output_file: str | None = None
    diagnostics: str | None = None


class PipelineState:
    """Tracks pipeline execution state via pipeline-state.json."""

    def __init__(self, run_dir: Path) -> None:  # noqa: D107
        self.run_dir = run_dir
        self._state_file = run_dir / "pipeline-state.json"
        self._completed: dict[str, StepStatus] = {}
        self._created_at: str | None = None
        if self._state_file.exists():
            self._load()
        else:
            self._created_at = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _load(self) -> None:
        """Load state from disk."""
        data = json.loads(self._state_file.read_text())
        self._created_at = data.get("created_at")
        for entry in data.get("steps", []):
            self._completed[entry["name"]] = StepStatus(**entry)

    def _save(self) -> None:
        """Persist state to disk."""
        now = datetime.now(tz=UTC)
        now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        # Always compute elapsed from created_at — useful even for
        # incomplete/crashed runs (shows how far we got before dying).
        elapsed: float | None = None
        if self._created_at:
            try:
                created = datetime.strptime(self._created_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
                elapsed = round((now - created).total_seconds(), 1)
            except ValueError:
                pass
        data = {
            "created_at": self._created_at,
            "updated_at": now_str,
            "completed_at": now_str if self.all_complete() else None,
            "elapsed_seconds": elapsed,
            "steps": [
                {
                    "name": s.name,
                    "status": s.status,
                    "started_at": s.started_at,
                    "completed_at": s.completed_at,
                    "elapsed_seconds": s.elapsed_seconds,
                    "output_file": s.output_file,
                    "diagnostics": s.diagnostics,
                }
                for s in self._completed.values()
            ],
        }
        self._state_file.write_text(json.dumps(data, indent=2) + "\n")

    def is_complete(self, step_name: str) -> bool:
        """Check if a step has been completed successfully."""
        entry = self._completed.get(step_name)
        return entry is not None and entry.status == "complete"

    def mark_started(self, step_name: str) -> None:
        """Record a step as started (running)."""
        self._completed[step_name] = StepStatus(
            name=step_name,
            status="running",
            started_at=datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        self._save()

    def mark_complete(
        self,
        step_name: str,
        output_file: str | None = None,
        diagnostics: str | None = None,
    ) -> None:
        """Record a step as successfully completed."""
        now = datetime.now(tz=UTC)
        now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        existing = self._completed.get(step_name)
        started = existing.started_at if existing else now_str
        # Compute elapsed from started_at
        elapsed: float | None = None
        if started:
            try:
                start_dt = datetime.strptime(started, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
                elapsed = (now - start_dt).total_seconds()
            except ValueError:
                pass
        self._completed[step_name] = StepStatus(
            name=step_name,
            status="complete",
            started_at=started,
            completed_at=now_str,
            elapsed_seconds=round(elapsed, 1) if elapsed is not None else None,
            output_file=output_file,
            diagnostics=diagnostics,
        )
        self._save()

    def mark_failed(self, step_name: str, diagnostics: str) -> None:
        """Record a step as failed."""
        now = datetime.now(tz=UTC)
        now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        existing = self._completed.get(step_name)
        started = existing.started_at if existing else now_str
        elapsed: float | None = None
        if started:
            try:
                start_dt = datetime.strptime(started, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
                elapsed = (now - start_dt).total_seconds()
            except ValueError:
                pass
        self._completed[step_name] = StepStatus(
            name=step_name,
            status="failed",
            started_at=started,
            completed_at=now_str,
            elapsed_seconds=round(elapsed, 1) if elapsed is not None else None,
            diagnostics=diagnostics,
        )
        self._save()

    def next_step(self) -> StepDefinition | None:
        """Determine the next step to execute.

        Returns the first step in PIPELINE_STEPS whose prerequisites are
        met and which hasn't been completed yet. Returns None if all steps
        are done.
        """
        for step in PIPELINE_STEPS:
            if self.is_complete(step.name):
                continue
            # Check prerequisites
            prereqs_met = True
            for req in step.requires:
                if not (self.run_dir / req).exists():
                    prereqs_met = False
                    break
            if prereqs_met:
                return step
        return None

    def all_complete(self) -> bool:
        """Check if all pipeline steps have been completed."""
        return all(self.is_complete(s.name) for s in PIPELINE_STEPS)

    def summary(self) -> dict[str, Any]:
        """Return a summary of pipeline progress."""
        total = len(PIPELINE_STEPS)
        completed = sum(1 for s in PIPELINE_STEPS if self.is_complete(s.name))
        failed = sum(1 for s in self._completed.values() if s.status == "failed")
        return {
            "total_steps": total,
            "completed": completed,
            "failed": failed,
            "remaining": total - completed - failed,
            "next_step": (ns.name if (ns := self.next_step()) else None),
        }
