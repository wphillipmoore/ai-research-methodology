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
from typing import Any

from mcp.server.fastmcp import FastMCP

from diogenes.config import ConfigError, load_config
from diogenes.search import fetch_page_extract
from diogenes.search_providers import BraveSearchProvider, GoogleSearchProvider, SerperSearchProvider

server = FastMCP(
    "Diogenes Research Tools",
    instructions=(
        "Diogenes provides web search and page fetching tools for research. "
        "Use dio_search to execute web searches via the configured search "
        "provider (Serper, Brave, or Google). Use dio_fetch to retrieve and "
        "extract text content from a URL. These tools avoid the expensive "
        "AI web search tool by executing searches in Python."
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
    name="dio_search",
    description=(
        "Execute a web search using the configured search provider "
        "(Serper/Google results by default). Returns titles, URLs, and "
        "snippets. Use this instead of web_search to save tokens — "
        "results are fetched by Python, not by the AI."
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
    results, total = provider.search(query, max_results=max_results)

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
        "Fetch a web page and extract the visible text content. "
        "Returns the first ~2000 characters of text, suitable for "
        "evaluating source quality and relevance without loading "
        "the full page into the AI context."
    ),
)
def dio_fetch(url: str) -> str:
    """Fetch a URL and return a text extract.

    Args:
        url: The URL to fetch.

    Returns:
        Extracted text content (first ~2000 chars), or error message.

    """
    content = fetch_page_extract(url)
    if not content:
        return json.dumps({"error": True, "message": f"Could not fetch content from {url}"})

    output: dict[str, Any] = {
        "url": url,
        "content_length": len(content),
        "content": content,
    }
    return json.dumps(output, indent=2)


@server.tool(
    name="dio_search_batch",
    description=(
        "Execute multiple web searches at once. Takes a list of query "
        "strings and returns results for all of them. More efficient "
        "than calling dio_search repeatedly."
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
        results, total = provider.search(query, max_results=max_results_per_query)
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


def main() -> None:
    """Run the MCP server."""
    server.run()


if __name__ == "__main__":
    main()
