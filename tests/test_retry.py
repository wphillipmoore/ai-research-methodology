"""Tests for retry module."""

from unittest.mock import MagicMock

import anthropic
import pytest
import requests

from diogenes.retry import (
    is_retriable_anthropic,
    is_retriable_http,
    retry_with_backoff,
)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep retry tests fast — suppress real sleeps and jitter randomness."""
    monkeypatch.setattr("diogenes.retry.time.sleep", lambda _s: None)
    monkeypatch.setattr("diogenes.retry.random.uniform", lambda _a, _b: 0.0)


class _TransientError(Exception):
    """Stand-in retriable exception for retry-loop tests."""


class _FatalError(Exception):
    """Stand-in non-retriable exception for retry-loop tests."""


def _is_transient(exc: BaseException) -> bool:
    return isinstance(exc, _TransientError)


class TestRetryWithBackoff:
    """Tests for the retry loop itself."""

    def test_success_first_attempt(self) -> None:
        call = MagicMock(return_value="ok")
        result = retry_with_backoff(call, is_retriable=_is_transient)
        assert result == "ok"
        assert call.call_count == 1

    def test_retries_then_succeeds(self) -> None:
        call = MagicMock(side_effect=[_TransientError(), _TransientError(), "ok"])
        result = retry_with_backoff(call, is_retriable=_is_transient, max_attempts=3)
        assert result == "ok"
        assert call.call_count == 3

    def test_exhausts_retries_and_raises(self) -> None:
        call = MagicMock(side_effect=_TransientError("third"))
        with pytest.raises(_TransientError, match="third"):
            retry_with_backoff(call, is_retriable=_is_transient, max_attempts=3)
        assert call.call_count == 3

    def test_non_retriable_raises_immediately(self) -> None:
        call = MagicMock(side_effect=[_FatalError("nope")])
        with pytest.raises(_FatalError, match="nope"):
            retry_with_backoff(call, is_retriable=_is_transient, max_attempts=3)
        # Only the first attempt ran — we don't retry non-retriable errors
        assert call.call_count == 1

    def test_delay_is_capped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Delay doubles on each failure but is clamped to max_delay."""
        sleeps: list[float] = []
        monkeypatch.setattr("diogenes.retry.time.sleep", sleeps.append)

        call = MagicMock(side_effect=[_TransientError(), _TransientError(), "ok"])
        retry_with_backoff(
            call,
            is_retriable=_is_transient,
            max_attempts=3,
            base_delay=10.0,
            max_delay=15.0,
        )
        # First retry: 10s. Second retry: min(20s, cap 15s) = 15s.
        assert sleeps == [10.0, 15.0]


class TestIsRetriableAnthropic:
    """Exception classifier for the anthropic SDK."""

    def test_connection_error(self) -> None:
        exc = anthropic.APIConnectionError(request=MagicMock())
        assert is_retriable_anthropic(exc) is True

    def test_timeout(self) -> None:
        exc = anthropic.APITimeoutError(request=MagicMock())
        assert is_retriable_anthropic(exc) is True

    @pytest.mark.parametrize("status", [429, 502, 503, 504, 529])
    def test_retriable_status_codes(self, status: int) -> None:
        exc = MagicMock(spec=anthropic.APIStatusError)
        exc.status_code = status
        assert is_retriable_anthropic(exc) is True

    @pytest.mark.parametrize("status", [400, 401, 403, 404, 418, 500])
    def test_non_retriable_status_codes(self, status: int) -> None:
        exc = MagicMock(spec=anthropic.APIStatusError)
        exc.status_code = status
        assert is_retriable_anthropic(exc) is False

    def test_unrelated_exception(self) -> None:
        assert is_retriable_anthropic(ValueError("nope")) is False


class TestIsRetriableHttp:
    """Exception classifier for the requests library."""

    def test_timeout(self) -> None:
        assert is_retriable_http(requests.Timeout()) is True

    def test_connection_error(self) -> None:
        assert is_retriable_http(requests.ConnectionError()) is True

    @pytest.mark.parametrize("status", [429, 502, 503, 504, 529])
    def test_retriable_http_status(self, status: int) -> None:
        resp = MagicMock()
        resp.status_code = status
        exc = requests.HTTPError()
        exc.response = resp
        assert is_retriable_http(exc) is True

    @pytest.mark.parametrize("status", [400, 401, 403, 404, 500])
    def test_non_retriable_http_status(self, status: int) -> None:
        resp = MagicMock()
        resp.status_code = status
        exc = requests.HTTPError()
        exc.response = resp
        assert is_retriable_http(exc) is False

    def test_http_error_without_response(self) -> None:
        exc = requests.HTTPError()
        exc.response = None
        assert is_retriable_http(exc) is False

    def test_unrelated_exception(self) -> None:
        assert is_retriable_http(ValueError("nope")) is False
