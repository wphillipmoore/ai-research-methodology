"""Implementation of the 'dio run' command."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from diogenes.api_client import APIClient, SubAgentError
from diogenes.config import load_config
from diogenes.pipeline import (
    step2_generate_hypotheses,
    step3_design_searches,
    step4_execute_searches,
    write_step_output,
)
from diogenes.schema_validator import ValidationError, parse_input_file, validate_research_input
from diogenes.search_providers import BraveSearchProvider, GoogleSearchProvider

# Resolve prompts directory relative to repo root
_REPO_ROOT = Path(__file__).parent.parent.parent.parent
_PROMPTS_DIR = _REPO_ROOT / "prompts" / "sub-agents"


def _timestamp() -> str:
    """Generate a YYYY-MM-DD-HHMMSS timestamp."""
    now = datetime.now(tz=UTC)
    return now.strftime("%Y-%m-%d-%H%M%S")


def _create_run_group_dir(output_dir: Path, runs: int) -> tuple[Path, list[Path]]:
    """Create the run group directory structure.

    Args:
        output_dir: Base output directory for the research instance.
        runs: Number of independent runs.

    Returns:
        Tuple of (group_dir, list of run_dirs).

    """
    output_dir.mkdir(parents=True, exist_ok=True)

    group_name = _timestamp()
    group_dir = output_dir / group_name
    group_dir.mkdir()

    run_dirs = []
    # Zero-pad based on total runs
    width = len(str(runs))
    for i in range(1, runs + 1):
        run_dir = group_dir / f"run-{str(i).zfill(width)}"
        run_dir.mkdir()
        run_dirs.append(run_dir)

    return group_dir, run_dirs


def _write_research_input(output_dir: Path, data: dict[str, Any]) -> Path:
    """Write the research-input.json file.

    Args:
        output_dir: The research instance directory.
        data: The validated research input data.

    Returns:
        Path to the written file.

    """
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "research-input.json"
    if path.exists():
        print(f"ERROR: {path} already exists. Use 'dio rerun' to re-execute.")
        print("To start new research, use a different output directory.")
        sys.exit(1)

    path.write_text(json.dumps(data, indent=2) + "\n")
    return path


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
    clarifier_prompt = _PROMPTS_DIR / "input-clarifier.md"

    try:
        clarified = client.call_sub_agent(
            prompt_path=clarifier_prompt,
            user_input=raw_input,
            output_schema="clarified-input.schema.json",
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


def _create_search_provider() -> BraveSearchProvider | GoogleSearchProvider | None:
    """Create a search provider from config.

    Returns the provider, or None on error (after printing).
    """
    cfg = load_config()

    if cfg.search_provider == "brave":
        if not cfg.brave_api_key:
            print("ERROR: Brave Search requires BRAVE_API_KEY in .dorc or .env")
            return None
        return BraveSearchProvider(cfg.brave_api_key)

    if cfg.search_provider == "google":
        if not cfg.google_api_key or not cfg.google_search_engine_id:
            print("ERROR: Google Search requires GOOGLE_API_KEY and GOOGLE_SEARCH_ENGINE_ID")
            return None
        return GoogleSearchProvider(cfg.google_api_key, cfg.google_search_engine_id)

    print(f"ERROR: Unknown search provider: {cfg.search_provider}")
    return None


def execute(input_file: str, output: str, runs: int) -> int:
    """Execute the 'dio run' command.

    Args:
        input_file: Path to the input file (JSON or text).
        output: Output directory path.
        runs: Number of independent runs.

    Returns:
        Exit code (0 for success, non-zero for failure).

    """
    output_dir = Path(output)
    input_path = Path(input_file)

    # Initialize API client (reused for all sub-agent calls)
    try:
        client = APIClient()
    except SubAgentError as e:
        print(f"ERROR: {e}")
        return 1

    # Initialize search provider
    search_provider = _create_search_provider()
    if search_provider is None:
        return 1

    # Step 1: Parse input and clarify via sub-agent if needed
    research_input = _parse_and_clarify(input_path, client)
    if research_input is None:
        return 1

    # Step 3: Write research-input.json
    print(f"Output directory: {output_dir}")
    input_json_path = _write_research_input(output_dir, research_input)
    print(f"  Wrote: {input_json_path}")

    # Step 4: Create run group directory structure
    print(f"Creating run group (runs={runs})...")
    group_dir, run_dirs = _create_run_group_dir(output_dir, runs)
    print(f"  Run group: {group_dir.name}")
    for rd in run_dirs:
        print(f"  Created: {rd.name}/")

    # Step 5: Save methodology snapshots
    prompt_snapshot_src = _REPO_ROOT / "ai-research-methodology" / "skills" / "research" / "prompts" / "research.md"
    if prompt_snapshot_src.exists():
        snapshot_dest = group_dir / "prompt-snapshot.md"
        snapshot_dest.write_text(prompt_snapshot_src.read_text())
        print("  Saved: prompt-snapshot.md")

    # --- Pipeline execution ---
    for run_dir in run_dirs:
        print()
        print(f"=== {run_dir.name} ===")

        # Step 2: Generate competing hypotheses
        print("Step 2: Generating competing hypotheses...")
        try:
            hypotheses = step2_generate_hypotheses(research_input, client)
        except SubAgentError as e:
            print(f"ERROR: {e}")
            return 1

        hyp_path = write_step_output(run_dir, "hypotheses.json", hypotheses)
        print(f"  Wrote: {hyp_path}")

        # Step 3: Design discriminating searches
        print("Step 3: Designing search plans...")
        try:
            search_plans = step3_design_searches(research_input, hypotheses, client)
        except SubAgentError as e:
            print(f"ERROR: {e}")
            return 1

        plan_path = write_step_output(run_dir, "search-plans.json", search_plans)
        print(f"  Wrote: {plan_path}")

        # Step 4: Execute searches and log
        print("Step 4: Executing searches...")
        try:
            search_results = step4_execute_searches(
                research_input, search_plans, client, search_provider,
            )
        except SubAgentError as e:
            print(f"ERROR: {e}")
            return 1

        results_path = write_step_output(run_dir, "search-results.json", search_results)
        print(f"  Wrote: {results_path}")

        # Steps 5-11: not yet implemented
        print()
        print(f"  Pipeline paused after step 4 for {run_dir.name}.")
        print("  Steps 5-11 not yet implemented.")

    # Write usage report
    usage_data = client.usage.to_dict()
    usage_path = write_step_output(group_dir, "usage.json", usage_data)

    print()
    print(f"Research complete. Output: {group_dir}")
    print()
    totals = usage_data["totals"]
    print(f"Usage: {totals['api_calls']} API calls, "
          f"{totals['input_tokens']:,} input + {totals['output_tokens']:,} output "
          f"= {totals['total_tokens']:,} tokens")
    if totals["web_search_requests"]:
        print(f"  Web: {totals['web_search_requests']} searches, "
              f"{totals['web_fetch_requests']} fetches")
    print(f"  Details: {usage_path}")

    return 0
