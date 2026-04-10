"""Research pipeline steps.

Each step function takes the accumulated research state and an API client,
calls the appropriate sub-agent for each item, and returns the enriched state.
The coordinator (run command) calls these in sequence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from diogenes.api_client import APIClient

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts" / "sub-agents"


def step2_generate_hypotheses(
    research_input: dict[str, Any],
    client: APIClient,
) -> dict[str, Any]:
    """Generate competing hypotheses for each claim and query.

    Loops over claims and queries from the clarified input. For each item,
    passes the item and axioms to the hypothesis-generator sub-agent. Enriches
    the research state with hypothesis data per item.

    Args:
        research_input: The clarified research input (output of step 1).
        client: Configured API client with common guidelines loaded.

    Returns:
        A dict mapping item IDs to their hypothesis results.

    Raises:
        SubAgentError: If a sub-agent call fails.

    """
    prompt_path = _PROMPTS_DIR / "hypothesis-generator.md"
    axioms = research_input.get("axioms", [])
    results: dict[str, Any] = {}

    claims = research_input.get("claims", [])
    queries = research_input.get("queries", [])

    for claim in claims:
        item_id = claim["id"]
        print(f"  Generating hypotheses for {item_id}: {claim['clarified_text'][:60]}...")

        agent_input = {
            "mode": "claim",
            "item": claim,
            "axioms": axioms,
        }

        response = client.call_sub_agent(
            prompt_path=prompt_path,
            user_input=agent_input,
            output_schema="hypotheses.schema.json",
        )

        results[item_id] = response
        _print_hypothesis_summary(item_id, response)

    for query in queries:
        item_id = query["id"]
        print(f"  Generating hypotheses for {item_id}: {query['clarified_text'][:60]}...")

        agent_input = {
            "mode": "query",
            "item": query,
            "axioms": axioms,
        }

        response = client.call_sub_agent(
            prompt_path=prompt_path,
            user_input=agent_input,
            output_schema="hypotheses.schema.json",
        )

        results[item_id] = response
        _print_hypothesis_summary(item_id, response)

    return results


def _print_hypothesis_summary(item_id: str, response: dict[str, Any]) -> None:
    """Print a brief summary of hypothesis generation results."""
    approach = response.get("approach", "unknown")
    if approach == "hypotheses":
        count = len(response.get("hypotheses", []))
        print(f"    {item_id}: {count} hypotheses generated")
    elif approach == "open-ended":
        count = len(response.get("search_themes", []))
        print(f"    {item_id}: open-ended, {count} search themes")
    else:
        print(f"    {item_id}: approach={approach}")


def write_step_output(
    output_dir: Path,
    filename: str,
    data: dict[str, Any] | list[Any],
) -> Path:
    """Write a pipeline step's output to a JSON file.

    Args:
        output_dir: Directory to write to.
        filename: Name of the JSON file.
        data: The data to serialize.

    Returns:
        Path to the written file.

    """
    path = output_dir / filename
    path.write_text(json.dumps(data, indent=2) + "\n")
    return path
