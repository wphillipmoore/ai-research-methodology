"""Tests for parallelize module."""

import time

from diogenes.parallelize import ExecutorResults, parallelize_process, parallelize_thread


def _add(a: int, b: int) -> int:
    return a + b


def _fail(msg: str) -> None:
    raise ValueError(msg)


def _slow(duration: float) -> str:
    time.sleep(duration)
    return "done"


class TestExecutorResults:
    """Tests for the ExecutorResults dataclass."""

    def test_empty(self) -> None:
        r = ExecutorResults()
        assert r.success_count == 0
        assert r.error_count == 0
        assert r.total == 0

    def test_with_results(self) -> None:
        r = ExecutorResults(results=[1, 2, 3])
        assert r.success_count == 3
        assert r.error_count == 0
        assert r.total == 3

    def test_with_exceptions(self) -> None:
        r = ExecutorResults(exceptions=[ValueError("x")])
        assert r.success_count == 0
        assert r.error_count == 1
        assert r.total == 1

    def test_mixed(self) -> None:
        r = ExecutorResults(results=[1, 2], exceptions=[ValueError("x")])
        assert r.success_count == 2
        assert r.error_count == 1
        assert r.total == 3


class TestParallelizeThread:
    """Tests for parallelize_thread."""

    def test_basic_parallel(self) -> None:
        kwargs_list = [{"a": 1, "b": 2}, {"a": 3, "b": 4}, {"a": 5, "b": 6}]
        results = parallelize_thread(_add, kwargs_list, max_workers=2)
        assert sorted(results.results) == [3, 7, 11]
        assert results.error_count == 0

    def test_empty_list(self) -> None:
        results = parallelize_thread(_add, [])
        assert results.results == []
        assert results.error_count == 0

    def test_single_item(self) -> None:
        results = parallelize_thread(_add, [{"a": 10, "b": 20}])
        assert results.results == [30]

    def test_collects_exceptions(self) -> None:
        kwargs_list = [{"msg": "fail1"}, {"msg": "fail2"}]
        results = parallelize_thread(_fail, kwargs_list, max_workers=2)
        assert results.success_count == 0
        assert results.error_count == 2
        assert all(isinstance(e, ValueError) for e in results.exceptions)

    def test_mixed_success_and_failure(self) -> None:
        def maybe_fail(x: int) -> int:
            if x < 0:
                msg = "negative"
                raise ValueError(msg)
            return x * 2

        kwargs_list = [{"x": 1}, {"x": -1}, {"x": 2}]
        results = parallelize_thread(maybe_fail, kwargs_list, max_workers=2)
        assert results.error_count == 1
        assert results.success_count == 2

    def test_max_workers_none(self) -> None:
        results = parallelize_thread(_add, [{"a": 1, "b": 1}], max_workers=None)
        assert results.results == [2]

    def test_progress_tracker(self) -> None:
        kwargs_list = [{"a": i, "b": i} for i in range(10)]
        results = parallelize_thread(_add, kwargs_list, max_workers=2, progress_tracker=5)
        assert results.success_count == 10


class TestParallelizeProcess:
    """Tests for parallelize_process."""

    def test_basic_parallel(self) -> None:
        kwargs_list = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
        results = parallelize_process(_add, kwargs_list, max_workers=2)
        assert sorted(results.results) == [3, 7]
        assert results.error_count == 0

    def test_empty_list(self) -> None:
        results = parallelize_process(_add, [])
        assert results.results == []

    def test_collects_exceptions(self) -> None:
        kwargs_list = [{"msg": "fail"}]
        results = parallelize_process(_fail, kwargs_list, max_workers=1)
        assert results.error_count == 1

    def test_caps_at_cpu_count(self) -> None:
        # Request more workers than CPUs — should not raise
        kwargs_list = [{"a": 1, "b": 1}]
        results = parallelize_process(_add, kwargs_list, max_workers=9999)
        assert results.results == [2]

    def test_max_workers_none(self) -> None:
        results = parallelize_process(_add, [{"a": 1, "b": 1}], max_workers=None)
        assert results.results == [2]

    def test_progress_tracker(self) -> None:
        kwargs_list = [{"a": i, "b": i} for i in range(6)]
        results = parallelize_process(_add, kwargs_list, max_workers=2, progress_tracker=3)
        assert results.success_count == 6
