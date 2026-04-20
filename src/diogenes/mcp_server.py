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

from mcp.server.fastmcp import FastMCP

from diogenes.config import ConfigError, load_config
from diogenes.events import get_mcp_logger, reconcile_run, reset_mcp_logger
from diogenes.renderer import render_run, render_run_group
from diogenes.search import FetchError, fetch_page_extract
from diogenes.search_providers import BraveSearchProvider, GoogleSearchProvider, SerperSearchProvider

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
    logger = get_mcp_logger()
    logger.run_id = run_id
    logger.set_output_dir(Path(output_dir))
    return json.dumps({"initialized": True, "output_dir": output_dir, "run_id": run_id})


@server.tool(
    name="dio_search",
    description=(
        "Execute a web search for the Diogenes research methodology. "
        "Returns titles, URLs, and snippets from the configured search "
        "provider. ONLY use this within /research workflows — do not use "
        "as a general web search replacement. Uses a limited search API quota."
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
        logger.log(
            step="step4_execute_searches",
            kind="search_error",
            detail=f"Search provider '{provider.name}' error for query '{query}': {exc}",
            layer="mcp",
        )
        return json.dumps({"error": True, "message": f"Search failed: {exc}", "query": query})

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
            logger.log(
                step="step4_execute_searches",
                kind="search_error",
                detail=f"Search provider '{provider.name}' error for query '{query}': {exc}",
                layer="mcp",
            )
            all_results.append({"query": query, "error": str(exc), "results": []})
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
        input_dir: Path to a run directory (with JSON files) or a run group
            directory (containing run-N/ subdirectories).
        output_dir: Path where the markdown tree should be written.

    Returns:
        JSON status report with paths and counts.

    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    if not input_path.exists():
        return json.dumps({"error": True, "message": f"Input directory not found: {input_dir}"})

    has_run_subdirs = any(d.is_dir() and d.name.startswith("run-") for d in input_path.iterdir())

    if has_run_subdirs:
        render_run_group(input_path, output_path)
        mode = "run-group"
    else:
        render_run(input_path, output_path)
        mode = "single-run"

    md_files = list(output_path.rglob("*.md"))
    return json.dumps(
        {
            "mode": mode,
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
