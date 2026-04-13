"""Research pipeline steps.

Each step function takes the accumulated research state and an API client,
calls the appropriate sub-agent for each item, and returns the enriched state.
The coordinator (run command) calls these in sequence.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from diogenes.search import SearchProvider, execute_search_plan, fetch_page_extract

if TYPE_CHECKING:
    from diogenes.api_client import APIClient

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts" / "sub-agents"

# Model overrides for cost optimization. Set to None to use the client default.
# Testing showed Haiku produces different verdicts than Sonnet on scoring steps,
# which changes downstream assessments. Correctness > cost. See issue #84.
_SCORING_MODEL: str | None = None


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


def step3_design_searches(
    research_input: dict[str, Any],
    hypotheses: dict[str, Any],
    client: APIClient,
) -> dict[str, Any]:
    """Design discriminating searches for each claim and query.

    For each item, passes the clarified item (with vocabulary) and its
    hypotheses to the search-designer sub-agent to produce a concrete
    search plan.

    Args:
        research_input: The clarified research input (output of step 1).
        hypotheses: The hypothesis results keyed by item ID (output of step 2).
        client: Configured API client with common guidelines loaded.

    Returns:
        A dict mapping item IDs to their search plan results.

    Raises:
        SubAgentError: If a sub-agent call fails.

    """
    prompt_path = _PROMPTS_DIR / "search-designer.md"
    results: dict[str, Any] = {}

    items = [*research_input.get("claims", []), *research_input.get("queries", [])]

    for item in items:
        item_id = item["id"]
        item_hypotheses = hypotheses.get(item_id, {})
        print(f"  Designing searches for {item_id}...")

        agent_input = {
            "item": item,
            "hypotheses": item_hypotheses,
        }

        response = client.call_sub_agent(
            prompt_path=prompt_path,
            user_input=agent_input,
            output_schema="search-plan.schema.json",
        )

        results[item_id] = response
        search_count = len(response.get("searches", []))
        approach = response.get("approach", "unknown")
        print(f"    {item_id}: {search_count} searches planned ({approach})")

    return results


_RELEVANCE_BATCH_SIZE = 5
_RELEVANCE_THRESHOLD = 5


def step4_execute_searches(
    research_input: dict[str, Any],
    search_plans: dict[str, Any],
    client: APIClient,
    search_provider: SearchProvider,
) -> dict[str, Any]:
    """Execute search plans and score results for each claim and query.

    Three phases:
    - 4A (Python): Execute searches via search provider. Zero LLM tokens.
    - 4B (LLM, batched): Score relevance 0-10 in batches of 5. Tiny calls.
    - 4C (Python): Sort by score, filter by threshold, deduplicate.

    Args:
        research_input: The clarified research input (output of step 1).
        search_plans: The search plans keyed by item ID (output of step 3).
        client: Configured API client with common guidelines loaded.
        search_provider: Search provider for executing web searches.

    Returns:
        A dict mapping item IDs to their search results.

    Raises:
        SubAgentError: If a sub-agent call fails.

    """
    scorer_prompt = _PROMPTS_DIR / "relevance-scorer.md"
    results: dict[str, Any] = {}

    items = [*research_input.get("claims", []), *research_input.get("queries", [])]

    for item in items:
        item_id = item["id"]
        item_plan = search_plans.get(item_id, {})
        searches = item_plan.get("searches", [])
        print(f"  Executing {len(searches)} searches for {item_id} via {search_provider.name}...")

        # Phase 4A: Python executes searches
        executions = execute_search_plan(item_plan, search_provider)
        total_results = sum(len(e.results) for e in executions)
        print(f"    {total_results} raw results from {len(executions)} searches")

        # Phase 4B: LLM scores relevance in batches
        all_scored = _score_results_batched(
            item,
            executions,
            client,
            scorer_prompt,
        )

        # Phase 4C: Python filters and deduplicates
        selected, rejected = _filter_and_deduplicate(all_scored)
        print(
            f"    {len(selected)} sources selected (score >= {_RELEVANCE_THRESHOLD}), {len(rejected)} below threshold"
        )

        results[item_id] = {
            "id": item_id,
            "searches_executed": [e.to_dict() for e in executions],
            "selected_sources": selected,
            "rejected_sources": rejected,
            "summary": {
                "total_searches": len(executions),
                "total_results_found": total_results,
                "total_selected": len(selected),
                "total_rejected": len(rejected),
                "relevance_threshold": _RELEVANCE_THRESHOLD,
            },
        }

    return results


def _score_results_batched(
    item: dict[str, Any],
    executions: list[Any],
    client: APIClient,
    scorer_prompt: Path,
) -> list[dict[str, Any]]:
    """Score all search results in batches via the relevance-scorer sub-agent."""
    all_scored: list[dict[str, Any]] = []

    for execution in executions:
        results_list = execution.results
        search_id = execution.search_id

        # Determine search intent from the execution
        search_intent = f"Search {search_id}: {' '.join(execution.terms[:3])}"

        # Process in batches
        for i in range(0, len(results_list), _RELEVANCE_BATCH_SIZE):
            batch = results_list[i : i + _RELEVANCE_BATCH_SIZE]
            batch_input = {
                "item_id": item["id"],
                "clarified_text": item.get("clarified_text", ""),
                "search_intent": search_intent,
                "results": [{"url": r.url, "title": r.title, "snippet": r.snippet} for r in batch],
            }

            response = client.call_sub_agent(
                prompt_path=scorer_prompt,
                user_input=batch_input,
                output_schema="relevance-scores.schema.json",
                include_guidelines=False,
                model=_SCORING_MODEL,
            )

            # Enrich scores with metadata from original results
            for score_entry in response.get("scores", []):
                score_entry["search_id"] = search_id
                # Find the original result for title/snippet
                for r in batch:
                    if r.url == score_entry["url"]:
                        score_entry["title"] = r.title
                        score_entry["snippet"] = r.snippet
                        score_entry["page_age"] = r.page_age
                        break
                all_scored.append(score_entry)

    return all_scored


def _filter_and_deduplicate(
    scored_results: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Filter by relevance threshold and deduplicate by URL."""
    # Sort by score descending
    scored_results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)

    seen_urls: set[str] = set()
    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for result in scored_results:
        url = result.get("url", "")
        score = result.get("relevance_score", 0)

        if url in seen_urls:
            continue
        seen_urls.add(url)

        if score >= _RELEVANCE_THRESHOLD:
            selected.append(result)
        else:
            rejected.append(result)

    return selected, rejected


_SCORING_BATCH_SIZE = 1
_MAX_SOURCES_TO_SCORE = 15


def step5_score_sources(
    research_input: dict[str, Any],
    search_results: dict[str, Any],
    client: APIClient,
) -> dict[str, Any]:
    """Score each selected source with reliability, relevance, and bias assessment.

    For each item, fetches page content (Python, zero tokens), then scores
    sources in batches of 3 via the source-scorer sub-agent.

    Args:
        research_input: The clarified research input (output of step 1).
        search_results: The search results keyed by item ID (output of step 4).
        client: Configured API client with common guidelines loaded.

    Returns:
        A dict mapping item IDs to their source scorecards.

    Raises:
        SubAgentError: If a sub-agent call fails.

    """
    scorer_prompt = _PROMPTS_DIR / "source-scorer.md"
    results: dict[str, Any] = {}

    items = [*research_input.get("claims", []), *research_input.get("queries", [])]

    for item in items:
        item_id = item["id"]
        item_results = search_results.get(item_id, {})
        all_selected = item_results.get("selected_sources", [])
        # Cap at top N by relevance score to control cost
        selected = all_selected[:_MAX_SOURCES_TO_SCORE]
        if len(all_selected) > _MAX_SOURCES_TO_SCORE:
            print(f"  Scoring top {len(selected)} of {len(all_selected)} sources for {item_id}...")
        else:
            print(f"  Scoring {len(selected)} sources for {item_id}...")

        # Phase A: Python fetches page content
        enriched_sources = []
        for source in selected:
            url = source.get("url", "")
            print(f"    Fetching {url[:60]}...")
            content = fetch_page_extract(url)
            enriched_sources.append(
                {
                    "url": url,
                    "title": source.get("title", ""),
                    "snippet": source.get("snippet", ""),
                    "content_extract": content,
                }
            )

        # Phase B: LLM scores in batches
        all_scorecards: list[dict[str, Any]] = []
        for i in range(0, len(enriched_sources), _SCORING_BATCH_SIZE):
            batch = enriched_sources[i : i + _SCORING_BATCH_SIZE]
            batch_input = {
                "item_id": item_id,
                "clarified_text": item.get("clarified_text", ""),
                "sources": batch,
            }

            response = client.call_sub_agent(
                prompt_path=scorer_prompt,
                user_input=batch_input,
                output_schema="source-scorecards.schema.json",
                max_tokens=8192,
                model=_SCORING_MODEL,
            )

            all_scorecards.extend(response.get("scorecards", []))

        print(f"    {item_id}: {len(all_scorecards)} sources scored")
        results[item_id] = {"id": item_id, "scorecards": all_scorecards}

    return results


def steps678_synthesize_and_assess(
    research_input: dict[str, Any],
    hypotheses: dict[str, Any],
    scorecards: dict[str, Any],
    client: APIClient,
) -> dict[str, Any]:
    """Synthesize evidence, assess, and identify gaps (Steps 6+7+8 combined).

    One LLM call per item. These steps are tightly coupled — synthesis informs
    assessment, assessment reveals gaps.

    Args:
        research_input: The clarified research input (output of step 1).
        hypotheses: Hypothesis results keyed by item ID (output of step 2).
        scorecards: Source scorecards keyed by item ID (output of step 5).
        client: Configured API client with common guidelines loaded.

    Returns:
        A dict mapping item IDs to their synthesis/assessment/gaps results.

    """
    prompt_path = _PROMPTS_DIR / "evidence-synthesizer.md"
    results: dict[str, Any] = {}

    items = [*research_input.get("claims", []), *research_input.get("queries", [])]

    for item in items:
        item_id = item["id"]
        item_hypotheses = hypotheses.get(item_id, {})
        item_scorecards = scorecards.get(item_id, {}).get("scorecards", [])
        print(f"  Synthesizing {item_id} ({len(item_scorecards)} sources)...")

        agent_input = {
            "item": item,
            "hypotheses": item_hypotheses,
            "scorecards": item_scorecards,
        }

        response = client.call_sub_agent(
            prompt_path=prompt_path,
            user_input=agent_input,
            output_schema="synthesis.schema.json",
            max_tokens=16384,
        )

        results[item_id] = response
        assessment = response.get("assessment", {})
        verdict = assessment.get("verdict", assessment.get("answer", ""))
        print(f"    {item_id}: {verdict[:80]}")

    return results


def step9_self_audit(
    research_input: dict[str, Any],
    hypotheses: dict[str, Any],
    search_results: dict[str, Any],
    scorecards: dict[str, Any],
    synthesis: dict[str, Any],
    client: APIClient,
) -> dict[str, Any]:
    """Self-audit, source-back verification, and reading list (Steps 9+9b+9c).

    One LLM call per item. Reviews the entire research chain.

    Args:
        research_input: Clarified research input (step 1).
        hypotheses: Hypothesis results (step 2).
        search_results: Search results (step 4).
        scorecards: Source scorecards (step 5).
        synthesis: Synthesis/assessment/gaps (steps 6-8).
        client: Configured API client.

    Returns:
        A dict mapping item IDs to their audit results.

    """
    prompt_path = _PROMPTS_DIR / "self-auditor.md"
    results: dict[str, Any] = {}

    items = [*research_input.get("claims", []), *research_input.get("queries", [])]

    for item in items:
        item_id = item["id"]
        print(f"  Auditing {item_id}...")

        agent_input = {
            "item": item,
            "hypotheses": hypotheses.get(item_id, {}),
            "search_results": search_results.get(item_id, {}),
            "scorecards": scorecards.get(item_id, {}).get("scorecards", []),
            "synthesis": synthesis.get(item_id, {}),
        }

        response = client.call_sub_agent(
            prompt_path=prompt_path,
            user_input=agent_input,
            output_schema="self-audit.schema.json",
            max_tokens=16384,
        )

        results[item_id] = response
        audit = response.get("process_audit", {})
        ratings = [
            audit.get("eligibility_criteria", {}).get("rating", "?"),
            audit.get("search_comprehensiveness", {}).get("rating", "?"),
            audit.get("evaluation_consistency", {}).get("rating", "?"),
            audit.get("synthesis_fairness", {}).get("rating", "?"),
        ]
        print(f"    {item_id}: audit [{', '.join(ratings)}]")

    return results


def step10_report(
    research_input: dict[str, Any],
    hypotheses: dict[str, Any],
    search_results: dict[str, Any],
    scorecards: dict[str, Any],
    synthesis: dict[str, Any],
    audit: dict[str, Any],
    client: APIClient,
) -> dict[str, Any]:
    """Assemble the final research report (Step 10).

    One LLM call per item. Pulls together all prior steps into a structured report.

    Args:
        research_input: Clarified research input (step 1).
        hypotheses: Hypothesis results (step 2).
        search_results: Search results (step 4).
        scorecards: Source scorecards (step 5).
        synthesis: Synthesis/assessment/gaps (steps 6-8).
        audit: Self-audit results (step 9).
        client: Configured API client.

    Returns:
        A dict mapping item IDs to their final reports.

    """
    prompt_path = _PROMPTS_DIR / "report-assembler.md"
    results: dict[str, Any] = {}

    claims = research_input.get("claims", [])
    queries = research_input.get("queries", [])
    items = [*claims, *queries]

    for item in items:
        item_id = item["id"]
        mode = "claim" if item_id.startswith("C") else "query"
        print(f"  Assembling report for {item_id} ({mode})...")

        agent_input = {
            "item": item,
            "hypotheses": hypotheses.get(item_id, {}),
            "search_results": search_results.get(item_id, {}),
            "scorecards": scorecards.get(item_id, {}).get("scorecards", []),
            "synthesis": synthesis.get(item_id, {}),
            "self_audit": audit.get(item_id, {}),
        }

        response = client.call_sub_agent(
            prompt_path=prompt_path,
            user_input=agent_input,
            output_schema="report.schema.json",
            max_tokens=16384,
        )

        results[item_id] = response
        verdict = response.get("assessment_summary", {}).get(
            "verdict",
            response.get("assessment_summary", {}).get("answer", ""),
        )
        print(f"    {item_id}: {verdict[:80]}")

    return results


def step11_archive(output_dir: Path, all_outputs: dict[str, Any]) -> Path:
    """Archive all research outputs for temporal revisitation (Step 11).

    Pure Python — no LLM call. Writes a single archive JSON with all
    pipeline outputs and metadata.

    Args:
        output_dir: The run directory to write to.
        all_outputs: Dict containing all pipeline step outputs.

    Returns:
        Path to the archive file.

    """
    archive = {
        "archived_at": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pipeline_version": "0.1.0",
        **all_outputs,
    }

    path = output_dir / "archive.json"
    path.write_text(json.dumps(archive, indent=2) + "\n")
    return path


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
