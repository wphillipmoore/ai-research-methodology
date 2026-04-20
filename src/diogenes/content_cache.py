"""Server-side content cache for fetched article bodies.

Retains the full text returned by fetch_page_extract() keyed by URL,
so downstream Python tools (dio_validate_packets, reconciler) can
access content without depending on the LLM to echo it through its
JSON output. The LLM can drop content_extract from scorecards — Python
retained it independently.

Lifecycle: created per-run via dio_init_run, populated as a side-effect
of dio_fetch, read by dio_validate_packets, discarded when the MCP
server process ends or reset_content_cache() is called.
"""

from __future__ import annotations


class ContentCache:
    """URL-keyed cache of fetched article bodies."""

    def __init__(self) -> None:  # noqa: D107
        self._store: dict[str, str] = {}

    def put(self, url: str, content: str) -> None:
        """Cache content for a URL (overwrites if already present)."""
        self._store[url] = content

    def get(self, url: str) -> str | None:
        """Retrieve cached content, or None if not cached."""
        return self._store.get(url)

    def has(self, url: str) -> bool:
        """Check if content is cached for a URL."""
        return url in self._store

    @property
    def urls(self) -> list[str]:
        """Return all cached URLs."""
        return list(self._store.keys())

    @property
    def size(self) -> int:
        """Number of cached entries."""
        return len(self._store)

    def clear(self) -> None:
        """Drop all cached content."""
        self._store.clear()


_cache: ContentCache | None = None


def get_content_cache() -> ContentCache:
    """Return the module-level content cache, creating if needed."""
    global _cache  # noqa: PLW0603
    if _cache is None:
        _cache = ContentCache()
    return _cache


def reset_content_cache() -> None:
    """Reset the content cache (between runs or for tests)."""
    global _cache  # noqa: PLW0603
    if _cache is not None:
        _cache.clear()
    _cache = None
