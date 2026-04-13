"""Search provider protocol and implementations.

Search execution is handled by Python, not by the LLM. This keeps token
costs manageable — the LLM only sees titles, URLs, and snippets for
result selection, not full page content.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import requests


@dataclass
class SearchResult:
    """A single search result from a provider."""

    title: str
    url: str
    snippet: str
    page_age: str | None = None


@dataclass
class SearchExecution:
    """Record of a single search execution (PRISMA log entry)."""

    search_id: str
    terms: list[str]
    provider: str
    date: str
    results: list[SearchResult]
    total_results_available: int

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        return {
            "search_id": self.search_id,
            "terms_used": self.terms,
            "provider": self.provider,
            "date": self.date,
            "results_found": len(self.results),
            "total_available": self.total_results_available,
            "results": [
                {
                    "title": r.title,
                    "url": r.url,
                    "snippet": r.snippet,
                    "page_age": r.page_age,
                }
                for r in self.results
            ],
        }


class SearchProvider(Protocol):
    """Protocol for search providers."""

    @property
    def name(self) -> str:
        """Provider name for logging."""
        ...

    def search(self, query: str, max_results: int = 10) -> tuple[list[SearchResult], int]:
        """Execute a search and return results.

        Args:
            query: The search query string.
            max_results: Maximum results to return.

        Returns:
            Tuple of (results list, total results available from provider).

        """
        ...


_FETCH_TIMEOUT = 10
_CONTENT_EXTRACT_LENGTH = 2000


def fetch_page_extract(url: str) -> str:
    """Fetch a page and return a text extract of the content.

    Returns the first ~2000 characters of visible text, or an empty
    string if the fetch fails. This is intentionally simple — we only
    need enough context for the scorer to assess quality and relevance.
    """
    try:
        resp = requests.get(
            url,
            timeout=_FETCH_TIMEOUT,
            headers={"User-Agent": "Diogenes/0.1 (research-methodology)"},
        )
        resp.raise_for_status()
    except (requests.RequestException, ValueError):
        return ""

    # Simple text extraction: strip HTML tags
    text = resp.text
    # Remove script and style blocks
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text[:_CONTENT_EXTRACT_LENGTH]


def execute_search_plan(
    search_plan: dict[str, Any],
    provider: SearchProvider,
    max_results_per_search: int = 5,
) -> list[SearchExecution]:
    """Execute all searches in a search plan using the given provider.

    Args:
        search_plan: The search plan from Step 3 (for one item).
        provider: The search provider to use.
        max_results_per_search: Maximum results to request per search.

    Returns:
        List of SearchExecution records (one per search in the plan).

    """
    executions: list[SearchExecution] = []
    searches = search_plan.get("searches", [])
    now = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    for search in searches:
        search_id = search.get("id", "S??")
        terms = search.get("terms", [])

        # Combine terms into a single query
        query = " ".join(terms[:3])

        results, total_available = provider.search(query, max_results=max_results_per_search)

        executions.append(
            SearchExecution(
                search_id=search_id,
                terms=terms,
                provider=provider.name,
                date=now,
                results=results,
                total_results_available=total_available,
            )
        )

    return executions
