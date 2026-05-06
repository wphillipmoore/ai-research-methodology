"""Search provider protocol and implementations.

Search execution is handled by Python, not by the LLM. This keeps token
costs manageable — the LLM only sees titles, URLs, and snippets for
result selection, not full page content.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import pypdf
import requests
import trafilatura

from diogenes.retry import is_retriable_http, retry_with_backoff


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


_FETCH_TIMEOUT = 15


class FetchError(Exception):
    """Raised when a page cannot be fetched or no article body can be extracted.

    Callers must catch this and decide whether to skip the source, retry,
    or abort — never silently substitute an empty string. An empty extract
    downstream becomes an invitation for the LLM to fabricate quotes from
    training-data memory of the URL.
    """


def _looks_like_pdf(url: str, content_type: str, body: bytes) -> bool:
    """Return True if the response is a PDF by any reliable signal."""
    # Content-Type is the primary signal; many academic hosts serve PDFs
    # correctly labeled.
    if "application/pdf" in content_type.lower():
        return True
    # PDF magic number is a belt-and-braces check for servers that mislabel
    # (e.g., serve application/octet-stream).
    if body[:5] == b"%PDF-":
        return True
    # URL suffix is the weakest signal — use only if everything else failed.
    # Some URLs end in .pdf but serve an HTML landing page; we still want
    # to try PDF extraction if the body looks like a PDF, and otherwise
    # fall through to HTML extraction.
    return url.lower().endswith(".pdf") and body[:5] == b"%PDF-"


def _extract_pdf(url: str, body: bytes) -> str:
    """Extract text from PDF bytes using pypdf. Raises FetchError on failure."""
    try:
        reader = pypdf.PdfReader(io.BytesIO(body))
        pages = [page.extract_text() or "" for page in reader.pages]
    except (pypdf.errors.PdfReadError, ValueError, OSError) as exc:  # ty: ignore[possibly-missing-submodule]
        msg = f"pypdf failed to parse PDF from {url}: {exc}"
        raise FetchError(msg) from exc

    text = "\n\n".join(p.strip() for p in pages if p and p.strip())
    if not text.strip():
        msg = (
            f"pypdf returned no text from {url} "
            f"({len(body)} bytes, {len(pages)} pages). "
            "The PDF may be scanned/image-only (no OCR applied) or encrypted."
        )
        raise FetchError(msg)

    return text.strip()


def _extract_html(url: str, html: str, status_code: int) -> str:
    """Extract article body from HTML via trafilatura. Raises FetchError on failure."""
    extracted = trafilatura.extract(
        html,
        url=url,
        favor_recall=True,
        include_comments=False,
        include_tables=True,
    )

    if not extracted or not extracted.strip():
        msg = (
            f"trafilatura returned no article body for {url} "
            f"(HTTP {status_code}, {len(html)} bytes HTML). "
            "The page may be JS-rendered, paywalled, or pure navigation."
        )
        raise FetchError(msg)

    return extracted.strip()


def fetch_page_extract(url: str) -> str:
    """Fetch a page and return the extracted article body as plain text.

    Routes by Content-Type / body magic: PDFs are extracted via pypdf,
    HTML via trafilatura. Both strip format-specific chrome (page headers,
    nav, running headers in PDFs) so the returned text is substantive
    article body. No truncation is applied — downstream token-cost concerns
    are addressed by reducing source count, not by chopping mid-article.

    Args:
        url: The URL to fetch.

    Returns:
        The extracted article body as plain text. Never the empty string —
        if extraction would yield nothing substantive, FetchError is raised
        instead so the caller can handle the failure explicitly.

    Raises:
        FetchError: The page could not be retrieved (network, HTTP error,
            timeout), or neither the PDF path nor the HTML path could
            extract substantive text (JS-rendered, paywalled, binary,
            scanned image PDF, encrypted PDF, etc.).

    """

    def fetch() -> requests.Response:
        resp = requests.get(
            url,
            timeout=_FETCH_TIMEOUT,
            headers={"User-Agent": "Diogenes/0.1 (research-methodology)"},
        )
        resp.raise_for_status()
        return resp

    try:
        resp = retry_with_backoff(fetch, is_retriable=is_retriable_http)
    except requests.RequestException as exc:
        msg = f"Fetch failed for {url}: {exc}"
        raise FetchError(msg) from exc
    except ValueError as exc:
        msg = f"Invalid URL or response decoding for {url}: {exc}"
        raise FetchError(msg) from exc

    content_type = resp.headers.get("Content-Type", "")
    if _looks_like_pdf(url, content_type, resp.content):
        return _extract_pdf(url, resp.content)

    return _extract_html(url, resp.text, resp.status_code)


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
