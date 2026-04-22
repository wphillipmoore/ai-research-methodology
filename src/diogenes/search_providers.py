"""Search provider implementations."""

from __future__ import annotations

from typing import Any

import requests

from diogenes.retry import is_retriable_http, retry_with_backoff
from diogenes.search import SearchResult

_DEFAULT_TIMEOUT = 10


class SerperSearchProvider:
    """Serper.dev search provider (Google results).

    Free tier: 2,500 queries/month. Simple JSON API.
    https://serper.dev/
    """

    API_URL = "https://google.serper.dev/search"

    def __init__(self, api_key: str) -> None:
        """Initialize with a Serper.dev API key."""
        self._api_key = api_key

    @property
    def name(self) -> str:
        """Provider name for logging."""
        return "serper"

    def search(self, query: str, max_results: int = 10) -> tuple[list[SearchResult], int]:
        """Execute a Serper.dev web search (Google results)."""
        headers = {
            "X-API-KEY": self._api_key,
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "q": query,
            "num": max_results,
        }

        def fetch() -> requests.Response:
            resp = requests.post(
                self.API_URL,
                headers=headers,
                json=payload,
                timeout=_DEFAULT_TIMEOUT,
            )
            resp.raise_for_status()
            return resp

        resp = retry_with_backoff(fetch, is_retriable=is_retriable_http)
        data = resp.json()

        organic = data.get("organic", [])
        # Serper doesn't return a total count; use organic length
        total = len(organic)

        results = [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("link", ""),
                snippet=r.get("snippet", ""),
                page_age=r.get("date"),
            )
            for r in organic
        ]

        return results, total


class BraveSearchProvider:
    """Brave Search API provider.

    Requires a BRAVE_API_KEY in config. Free tier: 2,000 queries/month.
    https://brave.com/search/api/
    """

    API_URL = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, api_key: str) -> None:
        """Initialize with a Brave Search API key."""
        self._api_key = api_key

    @property
    def name(self) -> str:
        """Provider name for logging."""
        return "brave"

    def search(self, query: str, max_results: int = 10) -> tuple[list[SearchResult], int]:
        """Execute a Brave web search."""
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self._api_key,
        }
        params: dict[str, Any] = {
            "q": query,
            "count": max_results,
        }

        def fetch() -> requests.Response:
            resp = requests.get(
                self.API_URL,
                headers=headers,
                params=params,
                timeout=_DEFAULT_TIMEOUT,
            )
            resp.raise_for_status()
            return resp

        resp = retry_with_backoff(fetch, is_retriable=is_retriable_http)
        data = resp.json()

        web_results = data.get("web", {}).get("results", [])
        total = data.get("web", {}).get("totalEstimatedMatches", len(web_results))

        results = [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=r.get("description", ""),
                page_age=r.get("page_age"),
            )
            for r in web_results
        ]

        return results, total


class GoogleSearchProvider:
    """Google Custom Search API provider.

    Requires GOOGLE_API_KEY and GOOGLE_SEARCH_ENGINE_ID in config.
    Free tier: 100 queries/day.
    https://developers.google.com/custom-search/v1/overview
    """

    API_URL = "https://www.googleapis.com/customsearch/v1"

    def __init__(self, api_key: str, search_engine_id: str) -> None:
        """Initialize with Google API key and Custom Search Engine ID."""
        self._api_key = api_key
        self._search_engine_id = search_engine_id

    @property
    def name(self) -> str:
        """Provider name for logging."""
        return "google"

    def search(self, query: str, max_results: int = 10) -> tuple[list[SearchResult], int]:
        """Execute a Google Custom Search."""
        params: dict[str, Any] = {
            "key": self._api_key,
            "cx": self._search_engine_id,
            "q": query,
            "num": min(max_results, 10),
        }

        def fetch() -> requests.Response:
            resp = requests.get(self.API_URL, params=params, timeout=_DEFAULT_TIMEOUT)
            resp.raise_for_status()
            return resp

        resp = retry_with_backoff(fetch, is_retriable=is_retriable_http)
        data = resp.json()

        items = data.get("items", [])
        total = int(data.get("searchInformation", {}).get("totalResults", len(items)))

        results = [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("link", ""),
                snippet=r.get("snippet", ""),
            )
            for r in items
        ]

        return results, total
