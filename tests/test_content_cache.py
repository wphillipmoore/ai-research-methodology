"""Tests for content_cache module."""

from diogenes.content_cache import ContentCache, get_content_cache, reset_content_cache


class TestContentCache:
    """Tests for the ContentCache class."""

    def test_put_and_get(self) -> None:
        cache = ContentCache()
        cache.put("https://example.com", "article body")
        assert cache.get("https://example.com") == "article body"

    def test_get_missing_returns_none(self) -> None:
        cache = ContentCache()
        assert cache.get("https://missing.com") is None

    def test_has_present(self) -> None:
        cache = ContentCache()
        cache.put("https://example.com", "body")
        assert cache.has("https://example.com") is True

    def test_has_absent(self) -> None:
        cache = ContentCache()
        assert cache.has("https://example.com") is False

    def test_urls_returns_all_keys(self) -> None:
        cache = ContentCache()
        cache.put("https://a.com", "a")
        cache.put("https://b.com", "b")
        assert set(cache.urls) == {"https://a.com", "https://b.com"}

    def test_urls_empty(self) -> None:
        cache = ContentCache()
        assert cache.urls == []

    def test_size(self) -> None:
        cache = ContentCache()
        assert cache.size == 0
        cache.put("https://a.com", "a")
        assert cache.size == 1
        cache.put("https://b.com", "b")
        assert cache.size == 2

    def test_clear(self) -> None:
        cache = ContentCache()
        cache.put("https://a.com", "a")
        cache.clear()
        assert cache.size == 0
        assert cache.get("https://a.com") is None

    def test_put_overwrites(self) -> None:
        cache = ContentCache()
        cache.put("https://a.com", "old")
        cache.put("https://a.com", "new")
        assert cache.get("https://a.com") == "new"
        assert cache.size == 1


class TestModuleSingleton:
    """Tests for module-level singleton functions."""

    def setup_method(self) -> None:
        reset_content_cache()

    def teardown_method(self) -> None:
        reset_content_cache()

    def test_get_content_cache_creates_singleton(self) -> None:
        cache = get_content_cache()
        assert isinstance(cache, ContentCache)
        assert get_content_cache() is cache

    def test_reset_content_cache_clears_and_nones(self) -> None:
        cache = get_content_cache()
        cache.put("https://a.com", "a")
        reset_content_cache()
        new_cache = get_content_cache()
        assert new_cache is not cache
        assert new_cache.size == 0

    def test_reset_content_cache_when_none(self) -> None:
        reset_content_cache()
        reset_content_cache()  # Should not raise
