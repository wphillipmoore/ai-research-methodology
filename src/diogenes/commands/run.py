"""Implementations of the 'dio run' and 'dio rerun' commands."""

from __future__ import annotations

import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from diogenes.api_client import APIClient, SubAgentError
from diogenes.config import load_config
from diogenes.events import EventLogger, reconcile_run
from diogenes.pipeline import (
    step2_generate_hypotheses,
    step3_design_searches,
    step4_execute_searches,
    step5_score_sources,
    step5b_extract_evidence,
    step9_self_audit,
    step10_report,
    step11_archive,
    steps678_synthesize_and_assess,
    write_step_output,
)
from diogenes.schema_validator import ValidationError, parse_input_file, validate_research_input
from diogenes.search_providers import BraveSearchProvider, GoogleSearchProvider, SerperSearchProvider
from diogenes.state_machine import PIPELINE_STEPS, PipelineState

# Resolve prompts from the package (works for both repo checkout and pip install)
_PACKAGE_DIR = Path(__file__).parent.parent
_PROMPTS_DIR = _PACKAGE_DIR / "prompts" / "sub-agents"

_INSTANCE_TIMESTAMP_FMT = "%Y-%m-%d-%H%M%S"
_INSTANCE_COLLISION_RETRIES = 3
_INSTANCE_COLLISION_SLEEP_SECONDS = 1.0


def _timestamp() -> str:
    """Generate a YYYY-MM-DD-HHMMSS timestamp (UTC)."""
    return datetime.now(tz=UTC).strftime(_INSTANCE_TIMESTAMP_FMT)


def _create_instance_dir(parent_dir: Path) -> Path:
    """Create a fresh timestamped instance subdirectory under parent_dir.

    Each invocation of ``dio run`` or ``dio rerun`` produces a new instance
    dir. The parent holds the immutable source input and one instance
    subdirectory per research execution.

    Collision handling: if two invocations land in the same second (rare
    but possible in scripted/back-to-back runs), sleep for 1s and retry
    up to a few times. We do not fall back to microsecond or suffix
    schemes — a plain timestamp is easier to eyeball when skimming the
    parent directory.
    """
    parent_dir.mkdir(parents=True, exist_ok=True)
    last_err: FileExistsError | None = None
    for _ in range(_INSTANCE_COLLISION_RETRIES):
        instance_dir = parent_dir / _timestamp()
        try:
            instance_dir.mkdir(parents=False, exist_ok=False)
        except FileExistsError as e:
            last_err = e
            time.sleep(_INSTANCE_COLLISION_SLEEP_SECONDS)
            continue
        return instance_dir
    msg = f"Could not create a unique instance dir under {parent_dir} after retries"
    raise RuntimeError(msg) from last_err


def _find_saved_input(parent_dir: Path) -> Path | None:
    """Locate the single source input file saved in parent_dir.

    ``dio run`` copies exactly one source input file into the parent. We
    identify it as the only regular (non-hidden) file there — instance
    subdirectories are directories, so they don't conflict.

    Returns None if zero or multiple candidates are present, letting the
    caller produce a clear error message.
    """
    candidates = [p for p in parent_dir.iterdir() if p.is_file() and not p.name.startswith(".")]
    if len(candidates) == 1:
        return candidates[0]
    return None


def _dispatch_step(
    step_def: Any,
    outputs: dict[str, Any],
    client: APIClient,
    search_provider: Any,
    event_logger: EventLogger,
    run_dir: Path,
) -> Any:
    """Dispatch a pipeline step to its handler function.

    Maps each step definition to the existing handler function with
    the correct arguments assembled from accumulated outputs. This is
    the per-step wiring that makes the generic state-machine loop work
    with the existing handler signatures.

    Returns the step's output dict, or None on failure.
    """
    ri = outputs["research_input"]
    name = step_def.name

    try:
        if name == "step_01_research_input_clarified":
            return ri  # Already done before the loop

        if name == "step_02_hypotheses":
            return step2_generate_hypotheses(ri, client)

        if name == "step_03_search_plans":
            return step3_design_searches(ri, outputs["hypotheses"], client)

        if name == "step_04_search_results":
            return step4_execute_searches(ri, outputs["search_plans"], client, search_provider, event_logger)

        if name == "step_05_scorecards":
            return step5_score_sources(ri, outputs["search_results"], client, event_logger)

        if name == "step_06_evidence_packets":
            return step5b_extract_evidence(ri, outputs["hypotheses"], outputs["scorecards"], client, event_logger)

        if name == "step_07_synthesis":
            return steps678_synthesize_and_assess(
                ri,
                outputs["hypotheses"],
                outputs["scorecards"],
                outputs["evidence_packets"],
                client,
            )

        if name == "step_08_self_audit":
            return step9_self_audit(
                ri,
                outputs["hypotheses"],
                outputs["search_results"],
                outputs["scorecards"],
                outputs["evidence_packets"],
                outputs["synthesis"],
                client,
            )

        if name == "step_09_reports":
            return step10_report(
                ri,
                outputs["hypotheses"],
                outputs["search_results"],
                outputs["scorecards"],
                outputs["synthesis"],
                outputs["self_audit"],
                client,
            )

        if name == "step_10_archive":
            all_outputs = {
                "run_metadata": {
                    "model": client.model,
                    "execution_path": "cli",
                    "run_id": run_dir.name,
                },
                **dict(outputs),
            }
            step11_archive(run_dir, all_outputs)
            # Archive writes its own file — return empty dict so the loop
            # doesn't try to re-serialize it.
            return {"_self_written": True}

        if name == "step_11_pipeline_events":
            coverage = reconcile_run(run_dir, event_logger)
            adherence = coverage.get("verbatim_adherence_pct")
            if adherence is not None:
                print(
                    f"  Coverage: {coverage['sources_scored']}/{coverage['sources_attempted']} "
                    f"sources, {adherence}% verbatim adherence"
                )
            event_logger.write()
            n_events = len(event_logger.events)
            if n_events:
                print(f"  Events: {n_events}")
            # Events file writes itself — return sentinel.
            return {"_self_written": True}

    except SubAgentError as e:
        print(f"ERROR: {e}")
        return None

    print(f"ERROR: Unknown step '{name}'")
    return None


def _parse_and_clarify(
    input_path: Path,
    client: APIClient,
) -> dict[str, Any] | None:
    """Parse the input file and clarify if needed (Step 1).

    Returns the research input dict, or None on error (after printing).
    """
    print(f"Reading input: {input_path}")
    try:
        raw_input = parse_input_file(input_path)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        return None

    # Route — JSON or text?
    if isinstance(raw_input, dict):
        print("Input format: JSON — validating schema...")
        try:
            research_input = validate_research_input(raw_input)
        except ValidationError as e:
            print(f"ERROR: {e}")
            return None
        print(f"  Claims: {len(research_input.get('claims', []))}")
        print(f"  Queries: {len(research_input.get('queries', []))}")
        print(f"  Axioms: {len(research_input.get('axioms', []))}")
        return research_input

    # Text input — call input-clarifier sub-agent
    print("Input format: text — calling input-clarifier sub-agent...")
    clarifier_prompt = _PROMPTS_DIR / "research-input-clarified.md"

    try:
        clarified = client.call_sub_agent(
            prompt_path=clarifier_prompt,
            user_input=raw_input,
            output_schema="research-input-clarified.schema.json",
        )
    except SubAgentError as e:
        print(f"ERROR: {e}")
        return None

    if clarified.get("error"):
        print(f"ERROR: Input clarifier failed: {clarified.get('message', 'unknown error')}")
        return None

    research_input = {
        "claims": clarified.get("claims", []),
        "queries": clarified.get("queries", []),
        "axioms": clarified.get("axioms", []),
    }

    claims_count = len(research_input.get("claims", []))
    queries_count = len(research_input.get("queries", []))
    axioms_count = len(research_input.get("axioms", []))
    print(f"  Clarified: {claims_count} claims, {queries_count} queries, {axioms_count} axioms")
    return research_input


def _create_search_provider() -> SerperSearchProvider | BraveSearchProvider | GoogleSearchProvider | None:
    """Create a search provider from config.

    Returns the provider, or None on error (after printing).
    """
    cfg = load_config()

    if cfg.search_provider == "serper":
        if not cfg.serper_api_key:
            print("ERROR: Serper.dev requires SERPER_API_KEY in .diorc or .env")
            print("  Sign up free at https://serper.dev/ (2,500 searches/month)")
            return None
        return SerperSearchProvider(cfg.serper_api_key)

    if cfg.search_provider == "brave":
        if not cfg.brave_api_key:
            print("ERROR: Brave Search requires BRAVE_API_KEY in .diorc or .env")
            return None
        return BraveSearchProvider(cfg.brave_api_key)

    if cfg.search_provider == "google":
        if not cfg.google_api_key or not cfg.google_search_engine_id:
            print("ERROR: Google Search requires GOOGLE_API_KEY and GOOGLE_SEARCH_ENGINE_ID")
            return None
        return GoogleSearchProvider(cfg.google_api_key, cfg.google_search_engine_id)

    print(f"ERROR: Unknown search provider: {cfg.search_provider}")
    return None


def _run_pipeline(parent_dir: Path, input_path: Path) -> int:
    """Execute the research pipeline for one instance.

    Shared by ``dio run`` (first-time invocation) and ``dio rerun``
    (subsequent instances). Creates a fresh timestamped instance
    subdirectory under parent_dir, runs Step 1 (clarify) to produce
    research-input-clarified.json *inside the instance dir*, then runs
    the remaining state-machine-driven steps.

    Clarification happens per-instance because the clarifier is an LLM
    step whose output may evolve over time as models improve. The source
    input (at parent_dir) is immutable; what we derive from it is
    deliberately re-derived for each instance.
    """
    try:
        client = APIClient()
    except SubAgentError as e:
        print(f"ERROR: {e}")
        return 1

    search_provider = _create_search_provider()
    if search_provider is None:
        return 1

    # Create a fresh timestamped instance subdirectory
    instance_dir = _create_instance_dir(parent_dir)
    print(f"Instance: {instance_dir}")

    # Step 1: parse & clarify the source input into this instance dir.
    # Intentionally run per-instance — clarifier output can drift as
    # models evolve, and each instance should capture its current form.
    research_input = _parse_and_clarify(input_path, client)
    if research_input is None:
        return 1
    clarified_path = write_step_output(instance_dir, "research-input-clarified.json", research_input)
    print(f"  Wrote: {clarified_path}")

    # Save methodology snapshot (common guidelines from the package)
    guidelines_src = _PACKAGE_DIR / "prompts" / "common-guidelines.md"
    if guidelines_src.exists():
        snapshot_dest = instance_dir / "prompt-snapshot.md"
        snapshot_dest.write_text(guidelines_src.read_text())
        print("  Saved: prompt-snapshot.md")

    # --- Pipeline execution (state-machine-driven) ---
    print()
    print(f"=== {instance_dir.name} ===")

    event_logger = EventLogger(
        run_id=instance_dir.name,
        output_dir=instance_dir,
        model=client.model,
        execution_path="cli",
    )

    state = PipelineState(instance_dir)

    # Accumulated step outputs — keyed by output filename stem.
    # Step 1 (clarify) is done before the loop; seed the outputs.
    outputs: dict[str, Any] = {"research_input": research_input}
    state.mark_complete("step_01_research_input_clarified", output_file="research-input-clarified.json")

    # Iterate the canonical step sequence from the state machine.
    for step_def in PIPELINE_STEPS:
        if state.is_complete(step_def.name):
            continue

        print(f"{step_def.display_name}...")
        state.mark_started(step_def.name)
        result = _dispatch_step(step_def, outputs, client, search_provider, event_logger, instance_dir)
        if result is None:
            state.mark_failed(step_def.name, diagnostics="Handler returned None")
            print(f"ERROR: {step_def.name} returned no result")
            return 1

        # Store the result and write to disk (unless the step wrote its own file)
        if step_def.output_file and not result.get("_self_written"):
            output_key = step_def.output_file.replace(".json", "").replace("-", "_")
            outputs[output_key] = result
            out_path = write_step_output(instance_dir, step_def.output_file, result)
            print(f"  Wrote: {out_path}")

        state.mark_complete(step_def.name, output_file=step_def.output_file)

    # Write usage report into the instance directory
    usage_data = client.usage.to_dict()
    usage_path = write_step_output(instance_dir, "usage.json", usage_data)

    print()
    print(f"Research complete. Output: {instance_dir}")
    print()
    totals = usage_data["totals"]
    cost = totals.get("estimated_cost_usd", 0)
    print(
        f"Usage: {totals['api_calls']} API calls, "
        f"{totals['input_tokens']:,} input + {totals['output_tokens']:,} output "
        f"= {totals['total_tokens']:,} tokens"
    )
    print(f"  Estimated cost: ${cost:.4f}")
    if totals["web_search_requests"]:
        print(f"  Web: {totals['web_search_requests']} searches, {totals['web_fetch_requests']} fetches")
    print(f"  Details: {usage_path}")

    return 0


def execute(input_file: str, output: str) -> int:
    """Execute the ``dio run`` command — first-time research invocation.

    Creates a fresh research container at ``output``, copies the source
    input file there, and runs one full instance of the research pipeline.

    ``output`` must not already exist with content. If it does, the user
    is told to use ``dio rerun`` to add a new instance to existing
    research — this prevents silently producing a new instance against
    a source input the user didn't mean to re-use.

    Args:
        input_file: Path to the input file (JSON or text markdown).
        output: Parent output directory (the research container). Must be
            fresh — either non-existent or empty.

    Returns:
        Exit code (0 for success, non-zero for failure).

    """
    parent_dir = Path(output)
    input_path = Path(input_file)

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        return 1

    # Refuse to silently reuse an existing research container. Directing
    # the user to `dio rerun` preserves the invariant that `dio run`
    # always establishes a new research definition from an explicit
    # input file.
    if parent_dir.exists() and any(parent_dir.iterdir()):
        print(f"ERROR: --output {parent_dir} already exists and is not empty.")
        print(
            "  Use 'dio rerun --output "
            f"{parent_dir}' to add a new instance to existing research,\n"
            "  or choose a different --output for a new research definition."
        )
        return 1

    # Establish the research container: create the parent and copy the
    # source input into it. The source is immutable once here;
    # per-instance state lives in timestamped subdirectories.
    parent_dir.mkdir(parents=True, exist_ok=True)
    src_dest = parent_dir / input_path.name
    shutil.copyfile(input_path, src_dest)
    print(f"Output directory: {parent_dir}")
    print(f"  Saved source input: {src_dest}")

    return _run_pipeline(parent_dir, src_dest)


def execute_rerun(output: str) -> int:
    """Execute the ``dio rerun`` command — new instance of existing research.

    Finds the saved source input in the parent output directory (copied
    there by a prior ``dio run``) and runs one full instance of the
    research pipeline using it. Each rerun produces a fresh timestamped
    instance, re-clarifying the input from scratch so the per-instance
    record reflects the current state of the models and tools.

    Args:
        output: Parent output directory (the research container). Must
            exist and contain a source input file from a prior ``dio run``.

    Returns:
        Exit code (0 for success, non-zero for failure).

    """
    parent_dir = Path(output)

    if not parent_dir.exists():
        print(f"ERROR: --output {parent_dir} does not exist.")
        print("  'dio rerun' requires a parent populated by a prior 'dio run'.")
        return 1

    input_path = _find_saved_input(parent_dir)
    if input_path is None:
        print(f"ERROR: Could not locate a single source input in {parent_dir}.")
        print("  Expected exactly one regular file (the input copied by 'dio run').")
        return 1

    print(f"Output directory: {parent_dir}")
    print(f"  Using saved source input: {input_path}")

    return _run_pipeline(parent_dir, input_path)
