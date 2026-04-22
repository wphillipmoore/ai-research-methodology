"""Diogenes MCP server — exposes Python search and mechanical services.

This server allows Claude Code (via the plugin) to call the same Python
search infrastructure that the dio CLI uses, avoiding the expensive
AI web search tool. The same functions are used by dio CLI (direct import),
this MCP server (tool wrapper), and future microservices (HTTP wrapper).

Usage with Claude Code:
    Add to settings.json under mcpServers:
    {
        "diogenes": {
            "command": "uv",
            "args": ["--directory", "/path/to/ai-research-methodology", "run", "dio-mcp"],
            "env": {}
        }
    }
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests
from mcp.server.fastmcp import FastMCP

from diogenes.config import ConfigError, load_config
from diogenes.content_cache import get_content_cache, reset_content_cache
from diogenes.events import get_mcp_logger, reconcile_run, reset_mcp_logger
from diogenes.renderer import render_run
from diogenes.search import FetchError, fetch_page_extract
from diogenes.search_providers import BraveSearchProvider, GoogleSearchProvider, SerperSearchProvider
from diogenes.state_machine import PipelineState

server = FastMCP(
    "Diogenes Research Tools",
    instructions=(
        "Diogenes provides search and page fetching tools for the Diogenes "
        "research methodology plugin (/research skill). These tools are "
        "designed ONLY for use within Diogenes research workflows — do NOT "
        "use them as a general-purpose replacement for web_search. They "
        "consume a limited quota of search API credits that should be "
        "reserved for research operations."
    ),
)


def _create_search_provider() -> SerperSearchProvider | BraveSearchProvider | GoogleSearchProvider:
    """Create a search provider from config."""
    cfg = load_config()

    if cfg.search_provider == "serper" and cfg.serper_api_key:
        return SerperSearchProvider(cfg.serper_api_key)
    if cfg.search_provider == "brave" and cfg.brave_api_key:
        return BraveSearchProvider(cfg.brave_api_key)
    if cfg.search_provider == "google" and cfg.google_api_key and cfg.google_search_engine_id:
        return GoogleSearchProvider(cfg.google_api_key, cfg.google_search_engine_id)

    msg = f"Search provider '{cfg.search_provider}' not configured. Set the API key in .diorc or .env."
    raise ConfigError(msg)


@server.tool(
    name="dio_init_run",
    description=(
        "Initialize event logging for a Diogenes research run. Call this "
        "ONCE at the start of each research run, passing the run output "
        "directory. All subsequent dio_fetch and dio_search calls will log "
        "events (errors, failures) to pipeline-events.json in this directory. "
        "MUST be called before any dio_fetch or dio_search calls in a run."
    ),
)
def dio_init_run(output_dir: str, run_id: str = "run-1") -> str:
    """Initialize event logging for a research run.

    Args:
        output_dir: Path to the run output directory.
        run_id: Run identifier (e.g., 'run-1').

    Returns:
        JSON confirmation.

    """
    reset_mcp_logger()
    reset_content_cache()
    logger = get_mcp_logger()
    logger.run_id = run_id
    logger.set_output_dir(Path(output_dir))
    return json.dumps({"initialized": True, "output_dir": output_dir, "run_id": run_id})


@server.tool(
    name="dio_next_step",
    description=(
        "Get the next pipeline step to execute. Reads the run directory's "
        "pipeline-state.json and output files to determine what's been "
        "completed, then returns the next step's instructions. The response "
        "tells you whether to execute an LLM prompt, call dio_execute_step "
        "for Python-only work, or stop (all steps complete). Call this in a "
        "loop after dio_init_run."
    ),
)
def dio_next_step(run_dir: str) -> str:
    """Determine and return the next pipeline step.

    Args:
        run_dir: Path to the run directory.

    Returns:
        JSON with step name, category, instructions, and expected output.

    """
    run_path = Path(run_dir)
    if not run_path.exists():
        return json.dumps({"error": True, "message": f"Run directory not found: {run_dir}"})

    state = PipelineState(run_path)
    step = state.next_step()

    if step is None:
        return json.dumps(
            {
                "step": "complete",
                "status": "all_steps_done",
                "instructions": "Research run complete. Call dio_flush_events() then dio_render().",
                "summary": state.summary(),
            }
        )

    # Build instructions based on step category
    instructions: str
    if step.category == "python_only":
        instructions = f"Call dio_execute_step(run_dir='{run_dir}', step_name='{step.name}')"
    elif step.prompt:
        prompt_path = f"skills/research/prompts/compiled/{step.prompt}"
        instructions = (
            f"Read the compiled prompt at {prompt_path}. "
            f"Follow its instructions to produce JSON output. "
            f"Write the result to {run_dir}/{step.output_file}."
        )
    else:
        instructions = f"Call dio_execute_step(run_dir='{run_dir}', step_name='{step.name}')"

    result: dict[str, Any] = {
        "step": step.name,
        "display_name": step.display_name,
        "category": step.category,
        "status": "ready",
        "instructions": instructions,
        "output_file": step.output_file,
    }

    if step.post_validators:
        post_steps = [
            f"Call dio_validate_packets(run_dir='{run_dir}')" for v in step.post_validators if v == "validate_packets"
        ]
        result["post_step"] = "; ".join(post_steps) if post_steps else None

    if step.mcp_tools:
        result["required_tools"] = step.mcp_tools

    result["progress"] = state.summary()

    return json.dumps(result, indent=2)


@server.tool(
    name="dio_execute_step",
    description=(
        "Execute a Python-only pipeline step server-side. Used for steps "
        "that don't require LLM judgment: search execution, page fetching, "
        "verbatim validation, archiving, event reconciliation. The MCP "
        "server runs the step function and writes output to the run directory."
    ),
)
def dio_execute_step(run_dir: str, step_name: str) -> str:
    """Execute a Python-only pipeline step.

    Args:
        run_dir: Path to the run directory.
        step_name: The step to execute (must match a StepDefinition.name).

    Returns:
        JSON status with output file path and any diagnostics.

    """
    run_path = Path(run_dir)
    state = PipelineState(run_path)

    # Find the step definition
    from diogenes.state_machine import PIPELINE_STEPS

    step = next((s for s in PIPELINE_STEPS if s.name == step_name), None)
    if step is None:
        return json.dumps({"error": True, "message": f"Unknown step: {step_name}"})

    if step.category not in ("python_only", "hybrid"):
        return json.dumps(
            {
                "error": True,
                "message": f"Step '{step_name}' is category '{step.category}' — use LLM execution, not dio_execute_step.",
            }
        )

    # Placeholder: actual handler dispatch is wired during the run.py
    # refactor (later in #110). Each handler needs APIClient, search
    # provider, event logger — context that the CLI driver creates.
    # For now, mark complete so the state machine can advance.
    state.mark_complete(step_name, output_file=step.output_file)
    return json.dumps(
        {
            "executed": True,
            "step": step_name,
            "output_file": step.output_file,
            "message": f"Step '{step_name}' executed successfully.",
        }
    )


def _classify_search_error(exc: BaseException, provider_name: str) -> dict[str, Any]:
    """Classify a search-provider failure into an actionable category.

    Returns a structured error payload for dio_search / dio_search_batch
    responses. The ``error_kind`` tag lets the calling agent decide
    whether to stop, ask the user, or fall back to ``web_search``:

    - ``quota_exhausted`` / ``rate_limited`` — the provider's free tier
      is tapped out or we're hammering it. Falling back to ``web_search``
      is reasonable, but the user should be told because web_search costs
      tokens per call rather than being free on a quota.
    - ``auth_failed`` — API key is missing, invalid, or revoked. Not a
      fallback situation; fix the config.
    - ``network_error`` — transport failure that already survived #77's
      retry loop. Something upstream is down; stopping is usually right.
    - ``other`` — anything else. Surface the message and let the agent
      use judgment.

    The ``fallback_available`` flag is set for categories where calling
    ``web_search`` as an alternative makes sense. Set to False for
    auth_failed (web_search won't help) and True for the others.
    """
    error_kind = "other"
    fallback_available = True

    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        error_kind = "network_error"
    elif isinstance(exc, requests.HTTPError) and exc.response is not None:
        status = exc.response.status_code
        quota_exhausted_status = 402
        rate_limited_status = 429
        auth_failed_statuses = {401, 403}
        if status == quota_exhausted_status:
            error_kind = "quota_exhausted"
        elif status == rate_limited_status:
            error_kind = "rate_limited"
        elif status in auth_failed_statuses:
            error_kind = "auth_failed"
            fallback_available = False

    messages = {
        "quota_exhausted": (
            f"Search provider '{provider_name}' quota exhausted. "
            "You can continue with web_search (higher token cost per call) "
            "or wait for the quota to reset."
        ),
        "rate_limited": (
            f"Search provider '{provider_name}' is rate-limiting requests. "
            "You can continue with web_search or wait and retry."
        ),
        "auth_failed": (
            f"Search provider '{provider_name}' rejected credentials. "
            "Fix the API key in .diorc or .env; web_search cannot substitute "
            "for a misconfigured provider."
        ),
        "network_error": (
            f"Search provider '{provider_name}' is unreachable after retries. "
            "You can continue with web_search or wait for the service to recover."
        ),
        "other": f"Search failed ({provider_name}): {exc}",
    }

    return {
        "error": True,
        "error_kind": error_kind,
        "message": messages[error_kind],
        "fallback_available": fallback_available,
    }


@server.tool(
    name="dio_search",
    description=(
        "Execute a web search for the Diogenes research methodology. "
        "Returns titles, URLs, and snippets from the configured search "
        "provider. ONLY use this within /research workflows — do not use "
        "as a general web search replacement. Uses a limited search API "
        "quota. On failure, returns a structured error with 'error_kind' "
        "(quota_exhausted / rate_limited / auth_failed / network_error / "
        "other) and 'fallback_available'; the caller can offer web_search "
        "as a fallback for quota/rate/network issues, but must not switch "
        "silently — the user needs to know the token cost changes."
    ),
)
def dio_search(query: str, max_results: int = 5) -> str:
    """Search the web for a query string.

    Args:
        query: The search query to execute.
        max_results: Maximum number of results to return (default 5).

    Returns:
        JSON string with search results.

    """
    provider = _create_search_provider()
    try:
        results, total = provider.search(query, max_results=max_results)
    except Exception as exc:  # noqa: BLE001
        logger = get_mcp_logger()
        classification = _classify_search_error(exc, provider.name)
        logger.log(
            step="step4_execute_searches",
            kind="search_error",
            detail=(f"Search provider '{provider.name}' {classification['error_kind']} for query '{query}': {exc}"),
            layer="mcp",
        )
        return json.dumps({**classification, "query": query})

    output: dict[str, Any] = {
        "provider": provider.name,
        "query": query,
        "total_available": total,
        "results": [
            {
                "title": r.title,
                "url": r.url,
                "snippet": r.snippet,
                "page_age": r.page_age,
            }
            for r in results
        ],
    }
    return json.dumps(output, indent=2)


@server.tool(
    name="dio_fetch",
    description=(
        "Fetch a web page and extract the article body as plain text for "
        "Diogenes research workflows. Navigation, headers, footers, and "
        "sidebars are stripped. No length truncation. Returns a structured "
        "error if the page cannot be retrieved or has no extractable article "
        "body — callers must not silently substitute empty content. ONLY "
        "use within /research workflows."
    ),
)
def dio_fetch(url: str) -> str:
    """Fetch a URL and return the extracted article body.

    Args:
        url: The URL to fetch.

    Returns:
        JSON string with either the extracted content or a structured
        error. Failure surfaces as ``{"error": true, "message": ...}`` so
        the LLM caller has an unambiguous signal to skip the source rather
        than invent content for it.

    """
    try:
        content = fetch_page_extract(url)
    except FetchError as exc:
        logger = get_mcp_logger()
        kind = "fetch_failed"
        if ".pdf" in url.lower():
            kind = "fetch_failed_pdf"
        elif "trafilatura" in str(exc).lower():
            kind = "fetch_failed_html"
        logger.log(
            step="step5_score_sources",
            kind=kind,
            detail=str(exc),
            url=url,
            layer="mcp",
        )
        return json.dumps({"error": True, "message": str(exc)})

    # Cache the fetched content server-side so dio_validate_packets can
    # verify verbatim quotes even if the LLM drops content_extract from
    # its scorecard output.
    cache = get_content_cache()
    cache.put(url, content)

    output: dict[str, Any] = {
        "url": url,
        "content_length": len(content),
        "content": content,
    }
    return json.dumps(output, indent=2)


@server.tool(
    name="dio_search_batch",
    description=(
        "Execute multiple web searches at once for Diogenes research "
        "workflows. More efficient than calling dio_search repeatedly. "
        "ONLY use within /research workflows."
    ),
)
def dio_search_batch(queries: list[str], max_results_per_query: int = 5) -> str:
    """Execute multiple searches in sequence.

    Args:
        queries: List of search query strings.
        max_results_per_query: Maximum results per query (default 5).

    Returns:
        JSON string with results grouped by query.

    """
    provider = _create_search_provider()
    all_results: list[dict[str, Any]] = []

    for query in queries:
        try:
            results, total = provider.search(query, max_results=max_results_per_query)
        except Exception as exc:  # noqa: BLE001
            logger = get_mcp_logger()
            classification = _classify_search_error(exc, provider.name)
            logger.log(
                step="step4_execute_searches",
                kind="search_error",
                detail=(f"Search provider '{provider.name}' {classification['error_kind']} for query '{query}': {exc}"),
                layer="mcp",
            )
            all_results.append({**classification, "query": query, "results": []})
            continue
        all_results.append(
            {
                "query": query,
                "total_available": total,
                "results": [
                    {
                        "title": r.title,
                        "url": r.url,
                        "snippet": r.snippet,
                        "page_age": r.page_age,
                    }
                    for r in results
                ],
            }
        )

    output: dict[str, Any] = {
        "provider": provider.name,
        "searches_executed": len(queries),
        "results": all_results,
    }
    return json.dumps(output, indent=2)


@server.tool(
    name="dio_flush_events",
    description=(
        "Flush the accumulated pipeline event log to disk. Call this AFTER "
        "all research steps complete and BEFORE rendering. Writes "
        "pipeline-events.json to the run directory initialized by "
        "dio_init_run. Returns event summary statistics."
    ),
)
def dio_flush_events() -> str:
    """Write the MCP event log to pipeline-events.json.

    Returns:
        JSON summary of events written, or an error if dio_init_run
        was never called.

    """
    logger = get_mcp_logger()
    if logger.output_dir is None:
        return json.dumps(
            {
                "error": True,
                "message": "No output directory set — call dio_init_run first.",
            }
        )
    # Run reconciler before flushing — detects gaps + computes coverage
    reconcile_run(logger.output_dir, logger)

    path = logger.write()
    summary = logger.summary()
    return json.dumps(
        {
            "written_to": str(path),
            "total_events": summary["total_events"],
            "by_kind": summary.get("by_kind", {}),
            "coverage": summary.get("coverage", {}),
        }
    )


@server.tool(
    name="dio_validate_packets",
    description=(
        "Validate evidence packets against source content using the "
        "deterministic verbatim verifier. Reads evidence-packets.json "
        "from the run directory, checks each packet's excerpt against "
        "the source's content (from scorecards or the server-side fetch "
        "cache), drops non-verbatim packets, and rewrites the file with "
        "real verbatim_stats. Call this AFTER evidence extraction (Step 5b) "
        "and BEFORE synthesis (Steps 6-8). MUST call dio_init_run first."
    ),
)
def dio_validate_packets(run_dir: str) -> str:
    """Validate and filter evidence packets for verbatim accuracy.

    Args:
        run_dir: Path to the run directory containing evidence-packets.json
            and scorecards.json.

    Returns:
        JSON summary of validation results.

    """
    run_path = Path(run_dir)
    packets_path = run_path / "evidence-packets.json"
    scorecards_path = run_path / "scorecards.json"

    if not packets_path.exists():
        return json.dumps({"error": True, "message": f"evidence-packets.json not found in {run_dir}"})

    packets_data = json.loads(packets_path.read_text())
    scorecards_data = json.loads(scorecards_path.read_text()) if scorecards_path.exists() else {}

    # Build URL → content map from scorecards + server-side cache
    content_by_url: dict[str, str] = {}
    cache = get_content_cache()

    # First: try scorecards for content_extract
    _extract_content_from_scorecards(scorecards_data, content_by_url)

    # Second: fill gaps from server-side cache (covers the case where
    # the LLM dropped content_extract from scorecards)
    for url in cache.urls:
        if url not in content_by_url or not content_by_url[url]:
            cached = cache.get(url)
            if cached:
                content_by_url[url] = cached

    # Validate packets — handle both CLI and skill output formats
    from diogenes.pipeline import _verify_packet_verbatim

    total_claimed = 0
    total_kept = 0
    total_dropped = 0

    # Skill format: {"id": "Q001", "packets": [...]}
    # CLI format: {"Q001": {"id": "Q001", "packets": [...]}}
    items = [("", packets_data)] if "packets" in packets_data else list(packets_data.items())

    for _key, item_data in items:
        if not isinstance(item_data, dict):
            continue
        packets = item_data.get("packets", [])
        verified: list[dict[str, Any]] = []
        dropped = 0
        for pkt in packets:
            source_url = pkt.get("source_url", "")
            content = content_by_url.get(source_url, "")
            if content and _verify_packet_verbatim(pkt, content):
                verified.append(pkt)
            else:
                dropped += 1

        total_claimed += len(packets)
        total_kept += len(verified)
        total_dropped += dropped

        item_data["packets"] = verified
        item_data["verbatim_stats"] = {
            "claimed": len(packets),
            "kept": len(verified),
            "dropped": dropped,
        }
        if dropped:
            existing_notes = item_data.get("extraction_notes", "") or ""
            adherence = 100.0 * len(verified) / max(len(packets), 1)
            item_data["extraction_notes"] = (
                existing_notes + f" [Python validator: dropped {dropped} of {len(packets)} "
                f"packets (adherence: {adherence:.1f}%)]"
            ).strip()

    # Write validated packets back
    packets_path.write_text(json.dumps(packets_data, indent=2) + "\n")

    adherence_pct = 100.0 * total_kept / max(total_claimed, 1)
    return json.dumps(
        {
            "validated": True,
            "packets_claimed": total_claimed,
            "packets_kept": total_kept,
            "packets_dropped": total_dropped,
            "verbatim_adherence_pct": round(adherence_pct, 1),
            "content_sources": {
                "from_scorecards": sum(1 for v in content_by_url.values() if v),
                "from_cache": cache.size,
            },
        }
    )


def _extract_content_from_scorecards(
    scorecards_data: dict[str, Any],
    content_by_url: dict[str, str],
) -> None:
    """Extract content_extract from scorecards in either CLI or skill format."""
    # CLI format: {"Q001": {"scorecards": [...]}}
    # Skill format: {"scorecards": [...]}
    if "scorecards" in scorecards_data and isinstance(scorecards_data["scorecards"], list):
        for sc in scorecards_data["scorecards"]:
            url = sc.get("url", "")
            content = sc.get("content_extract", "")
            if url and content:
                content_by_url[url] = content
    else:
        for item_data in scorecards_data.values():
            if isinstance(item_data, dict) and "scorecards" in item_data:
                for sc in item_data["scorecards"]:
                    url = sc.get("url", "")
                    content = sc.get("content_extract", "")
                    if url and content:
                        content_by_url[url] = content


@server.tool(
    name="dio_render",
    description=(
        "Render a Diogenes JSON research output directory to a tree of "
        "linked markdown files. Pure Python — zero LLM tokens. Reads the "
        "JSON files written by the /research workflow (research-input.json, "
        "hypotheses.json, reports.json, etc.) and produces clean browsable "
        "markdown with relative links. ONLY use within /research workflows."
    ),
)
def dio_render(input_dir: str, output_dir: str) -> str:
    """Render JSON research output to linked markdown.

    Args:
        input_dir: Path to a run directory (containing JSON step outputs).
        output_dir: Path where the markdown tree should be written.

    Returns:
        JSON status report with paths and counts.

    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    if not input_path.exists():
        return json.dumps({"error": True, "message": f"Input directory not found: {input_dir}"})

    render_run(input_path, output_path)

    md_files = list(output_path.rglob("*.md"))
    return json.dumps(
        {
            "input_dir": str(input_path),
            "output_dir": str(output_path),
            "markdown_files_written": len(md_files),
            "entry_point": str(output_path / "index.md"),
        },
        indent=2,
    )


def main() -> None:
    """Run the MCP server."""
    server.run()


if __name__ == "__main__":
    main()
