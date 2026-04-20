"""Pipeline event logger for deterministic observability.

Captures errors, drops, filtering decisions, and structural gaps as
structured events during a research run. Written by three layers:

- **MCP tools** (dio_fetch, dio_search) log infrastructure failures as
  side-effects — works on both CLI and skill paths, no LLM involvement.
- **Pipeline orchestrator** (pipeline.py) logs Python-side decisions
  like verbatim drops, threshold rejects, source caps — CLI path only.
- **Post-run reconciler** infers structural gaps by comparing step
  inputs and outputs — works on both paths.

The LLM never writes to this log. Every event is deterministic.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path  # noqa: TC003 — needed at runtime for Path operations
from typing import Any


class EventLogger:
    """Append-only structured event log for a single research run."""

    def __init__(  # noqa: D107
        self,
        run_id: str,
        output_dir: Path | None = None,
        model: str | None = None,
        execution_path: str = "cli",
    ) -> None:
        self.run_id = run_id
        self.output_dir = output_dir
        self.model = model
        self.execution_path = execution_path
        self._events: list[dict[str, Any]] = []
        self._coverage: dict[str, Any] = {}

    def log(  # noqa: PLR0913
        self,
        *,
        step: str,
        kind: str,
        detail: str,
        layer: str,
        item_id: str | None = None,
        url: str | None = None,
        count: int | None = None,
        score: float | None = None,
        threshold: float | None = None,
    ) -> None:
        """Record a single pipeline event."""
        event: dict[str, Any] = {
            "step": step,
            "kind": kind,
            "detail": detail,
            "timestamp": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "layer": layer,
        }
        if item_id is not None:
            event["item_id"] = item_id
        if url is not None:
            event["url"] = url
        if count is not None:
            event["count"] = count
        if score is not None:
            event["score"] = score
        if threshold is not None:
            event["threshold"] = threshold
        self._events.append(event)

    @property
    def events(self) -> list[dict[str, Any]]:
        """Return a copy of all recorded events."""
        return list(self._events)

    def summary(self) -> dict[str, Any]:
        """Compute aggregate statistics across all events."""
        by_kind: dict[str, int] = {}
        by_step: dict[str, int] = {}
        for ev in self._events:
            by_kind[ev["kind"]] = by_kind.get(ev["kind"], 0) + 1
            by_step[ev["step"]] = by_step.get(ev["step"], 0) + 1
        result: dict[str, Any] = {
            "total_events": len(self._events),
            "by_kind": by_kind,
            "by_step": by_step,
        }
        if self._coverage:
            result["coverage"] = self._coverage
        return result

    def to_dict(self) -> dict[str, Any]:
        """Serialize the full event log for JSON persistence."""
        result: dict[str, Any] = {
            "run_id": self.run_id,
            "run_metadata": {
                "model": self.model,
                "execution_path": self.execution_path,
            },
            "events": self._events,
            "summary": self.summary(),
        }
        return result

    def write(self, path: Path | None = None) -> Path:
        """Write the event log to disk.

        Args:
            path: Explicit output path. If None, writes to
                ``self.output_dir / "pipeline-events.json"``.

        Returns:
            The path written to.

        Raises:
            ValueError: If no output path is available.

        """
        if path is None:
            if self.output_dir is None:
                msg = "No output directory set — call set_output_dir() or pass path="
                raise ValueError(msg)
            path = self.output_dir / "pipeline-events.json"
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n")
        return path

    def set_output_dir(self, output_dir: Path) -> None:
        """Set or update the output directory (used by dio_init_run)."""
        self.output_dir = output_dir


def reconcile_run(run_dir: Path, logger: EventLogger) -> dict[str, Any]:
    """Post-run reconciler: detect structural gaps and compute coverage stats.

    Reads the JSON output files from a completed run, compares step inputs
    vs outputs, and emits reconciler events for any gaps. Also computes
    the ``coverage`` summary block (sources_attempted, sources_scored,
    packets_claimed, packets_verified, verbatim_adherence_pct) that the
    renderer uses to show adherence in the status line.

    Works on both CLI and skill paths — reads files only, no LLM.

    Args:
        run_dir: Path to the run directory containing JSON step outputs.
        logger: EventLogger to append reconciler events to.

    Returns:
        The coverage stats dict (also attached to logger's summary).

    """
    coverage: dict[str, Any] = {}

    search_results = _load_run_json(run_dir / "search-results.json")
    scorecards = _load_run_json(run_dir / "source-scorecards.json")
    evidence_packets = _load_run_json(run_dir / "evidence-packets.json")

    # --- Sources: selected → capped → fetched → scored ---
    # search-results has total_selected (passed relevance threshold).
    # The pipeline caps at _MAX_SOURCES_TO_SCORE before fetching.
    # Fetch failures reduce the cap further. Scorecards = survivors.
    #
    # We can't read the cap from the JSON (it's a pipeline constant),
    # so we compute "attempted at fetch" = scored + fetch failures from
    # the event log (these were already captured by Layer 1/2).
    sources_selected = 0
    for _item_id, item_data in _iter_items(search_results):
        selected = item_data.get("selected_sources", [])
        sources_selected += len(selected)

    sources_scored = 0
    for _item_id, item_data in _iter_items(scorecards):
        cards = item_data.get("scorecards", [])
        sources_scored += len(cards)

    # Count fetch failures already logged by Layer 1/2
    fetch_kinds = ("fetch_failed", "fetch_failed_pdf", "fetch_failed_html")
    n_fetch_failures = sum(1 for e in logger.events if e.get("kind") in fetch_kinds)
    sources_attempted_at_fetch = sources_scored + n_fetch_failures
    sources_capped = sources_selected - sources_attempted_at_fetch

    if sources_capped > 0:
        logger.log(
            step="reconciler",
            kind="source_capped",
            detail=(
                f"{sources_capped} of {sources_selected} selected sources "
                f"were beyond the scoring cap (top {sources_attempted_at_fetch} scored)"
            ),
            count=sources_capped,
            layer="reconciler",
        )

    coverage["sources_selected"] = sources_selected
    coverage["sources_attempted"] = sources_attempted_at_fetch
    coverage["sources_scored"] = sources_scored
    coverage["sources_dropped_fetch"] = n_fetch_failures
    coverage["sources_capped"] = sources_capped

    # --- Evidence packet coverage from verbatim_stats ---
    packets_claimed = 0
    packets_verified = 0
    packets_dropped = 0
    for _item_id, item_data in _iter_items(evidence_packets):
        stats = item_data.get("verbatim_stats", {})
        if stats:
            packets_claimed += stats.get("claimed", 0)
            packets_verified += stats.get("kept", 0)
            packets_dropped += stats.get("dropped", 0)

    coverage["packets_claimed"] = packets_claimed
    coverage["packets_verified"] = packets_verified
    coverage["packets_dropped"] = packets_dropped
    if packets_claimed > 0:
        coverage["verbatim_adherence_pct"] = round(100.0 * packets_verified / packets_claimed, 1)
    else:
        coverage["verbatim_adherence_pct"] = None

    # --- Missing expected step outputs ---
    expected_files = [
        "hypotheses.json",
        "search-plans.json",
        "search-results.json",
        "source-scorecards.json",
        "evidence-packets.json",
        "synthesis.json",
        "self-audit.json",
        "reports.json",
    ]
    for fname in expected_files:
        if not (run_dir / fname).exists():
            logger.log(
                step="reconciler",
                kind="missing_step_output",
                detail=f"Expected output file {fname} not found in run directory",
                layer="reconciler",
            )

    # Attach coverage to logger summary
    logger._coverage = coverage  # noqa: SLF001
    return coverage


def _load_run_json(path: Path) -> dict[str, Any]:
    """Load a JSON file, returning empty dict if missing or invalid."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _iter_items(
    data: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    """Iterate over per-item data in either CLI or plugin format.

    CLI format: ``{"Q001": {"id": "Q001", ...}, "C001": {...}}``
    Plugin format: ``{"id": "Q001", ...}`` (single item, flat)
    """
    if not data:
        return []
    if "id" in data and isinstance(data.get("id"), str):
        return [(data["id"], data)]
    return [(k, v) for k, v in data.items() if isinstance(v, dict) and v.get("id")]


# Module-level singleton for the MCP path. MCP tools import this and
# call log() as a side-effect. The CLI path creates its own instance
# in pipeline.py and passes it through the step functions.
_mcp_logger: EventLogger | None = None


def get_mcp_logger() -> EventLogger:
    """Return the module-level MCP event logger, creating if needed.

    The MCP logger is a singleton per server process. It starts without
    an output directory — ``dio_init_run`` sets the directory before
    research begins. Events logged before ``dio_init_run`` are buffered
    in memory and flushed when the directory is set.
    """
    global _mcp_logger  # noqa: PLW0603
    if _mcp_logger is None:
        _mcp_logger = EventLogger(run_id="mcp-session")
    return _mcp_logger


def reset_mcp_logger() -> None:
    """Reset the MCP logger (for tests or between runs)."""
    global _mcp_logger  # noqa: PLW0603
    _mcp_logger = None
