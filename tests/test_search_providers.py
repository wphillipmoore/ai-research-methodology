"""Tests for search_providers module."""

from unittest.mock import MagicMock, patch

from diogenes.search_providers import BraveSearchProvider, GoogleSearchProvider, SerperSearchProvider


class TestSerperSearchProvider:
    """Tests for SerperSearchProvider."""

    def test_name(self) -> None:
        p = SerperSearchProvider(api_key="test")
        assert p.name == "serper"

    @patch("diogenes.search_providers.requests.post")
    def test_search_success(self, mock_post: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "organic": [
                {"title": "Result 1", "link": "https://a.com", "snippet": "Snippet 1", "date": "2024-01"},
                {"title": "Result 2", "link": "https://b.com", "snippet": "Snippet 2"},
            ]
        }
        mock_post.return_value = mock_resp

        p = SerperSearchProvider(api_key="test-key")
        results, total = p.search("test query", max_results=5)

        assert len(results) == 2
        assert total == 2
        assert results[0].title == "Result 1"
        assert results[0].url == "https://a.com"
        assert results[0].page_age == "2024-01"
        assert results[1].page_age is None

        # Verify API call
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs.kwargs["headers"]["X-API-KEY"] == "test-key"

    @patch("diogenes.search_providers.requests.post")
    def test_search_empty(self, mock_post: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"organic": []}
        mock_post.return_value = mock_resp

        p = SerperSearchProvider(api_key="key")
        results, total = p.search("query")
        assert results == []
        assert total == 0


class TestBraveSearchProvider:
    """Tests for BraveSearchProvider."""

    def test_name(self) -> None:
        p = BraveSearchProvider(api_key="test")
        assert p.name == "brave"

    @patch("diogenes.search_providers.requests.get")
    def test_search_success(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "web": {
                "results": [
                    {"title": "R1", "url": "https://a.com", "description": "D1", "page_age": "2024-01-01"},
                ],
                "totalEstimatedMatches": 1000,
            }
        }
        mock_get.return_value = mock_resp

        p = BraveSearchProvider(api_key="test-key")
        results, total = p.search("test query")

        assert len(results) == 1
        assert total == 1000
        assert results[0].title == "R1"
        assert results[0].snippet == "D1"
        assert results[0].page_age == "2024-01-01"

    @patch("diogenes.search_providers.requests.get")
    def test_search_empty(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"web": {"results": []}}
        mock_get.return_value = mock_resp

        p = BraveSearchProvider(api_key="key")
        results, total = p.search("query")
        assert results == []
        assert total == 0


class TestGoogleSearchProvider:
    """Tests for GoogleSearchProvider."""

    def test_name(self) -> None:
        p = GoogleSearchProvider(api_key="key", search_engine_id="cx")
        assert p.name == "google"

    @patch("diogenes.search_providers.requests.get")
    def test_search_success(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "items": [
                {"title": "R1", "link": "https://a.com", "snippet": "S1"},
            ],
            "searchInformation": {"totalResults": "500"},
        }
        mock_get.return_value = mock_resp

        p = GoogleSearchProvider(api_key="key", search_engine_id="cx")
        results, total = p.search("test query")

        assert len(results) == 1
        assert total == 500
        assert results[0].title == "R1"
        assert results[0].url == "https://a.com"

    @patch("diogenes.search_providers.requests.get")
    def test_search_caps_at_10(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"items": [], "searchInformation": {"totalResults": "0"}}
        mock_get.return_value = mock_resp

        p = GoogleSearchProvider(api_key="key", search_engine_id="cx")
        p.search("query", max_results=20)

        call_kwargs = mock_get.call_args
        assert call_kwargs.kwargs["params"]["num"] == 10

    @patch("diogenes.search_providers.requests.get")
    def test_search_empty(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"items": []}
        mock_get.return_value = mock_resp

        p = GoogleSearchProvider(api_key="key", search_engine_id="cx")
        results, total = p.search("query")
        assert results == []
        assert total == 0
