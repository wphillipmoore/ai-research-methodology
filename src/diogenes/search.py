"""Search provider protocol and implementations.

Search execution is handled by Python, not by the LLM. This keeps token
costs manageable — the LLM only sees titles, URLs, and snippets for
result selection, not full page content.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol


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


def execute_search_plan(
    search_plan: dict[str, Any],
    provider: SearchProvider,
) -> list[SearchExecution]:
    """Execute all searches in a search plan using the given provider.

    Args:
        search_plan: The search plan from Step 3 (for one item).
        provider: The search provider to use.

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

        results, total_available = provider.search(query)

        executions.append(SearchExecution(
            search_id=search_id,
            terms=terms,
            provider=provider.name,
            date=now,
            results=results,
            total_results_available=total_available,
        ))

    return executions
