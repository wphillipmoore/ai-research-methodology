"""Thread- and process-based parallel execution with kwargs-style argument passing.

Wraps concurrent.futures executors with two features not available in
mainstream parallel libraries (joblib, tqdm, pqdm, MPIRE):

1. Native kwargs-style argument passing — accepts a sequence of dicts,
   each unpacked as **kwargs to the target function. Essential for
   calling functions with multiple named parameters.

2. Non-fatal error collection — collects exceptions alongside results
   rather than raising on first failure. The caller decides what to do
   with partial results.

Two execution modes:
- parallelize_thread: ThreadPoolExecutor (shared memory, lightweight).
  Use for I/O-bound work where the target function is thread-safe
  (e.g., Anthropic API calls via httpx).
- parallelize_process: ProcessPoolExecutor (separate memory per worker).
  Use when the target function or its dependencies are NOT thread-safe
  (e.g., trafilatura/lxml HTML parsing). Each process gets its own
  memory space, so native-library thread-safety is irrelevant.

The caller picks the mode based on whether the target function has
thread-safety constraints. The API is identical — swap one function
name and the parallelism model changes.

Origin: adapted from a shared collaboration between the project author
and Richie Cahill. Original source:
https://github.com/RichieCahill/dotfiles/blob/main/python/parallelize.py
"""

from __future__ import annotations

import logging
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass, field
from multiprocessing import cpu_count
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

logger = logging.getLogger(__name__)


@dataclass
class ExecutorResults:
    """Results of a parallel execution: successes and failures side by side."""

    results: list[Any] = field(default_factory=list)
    exceptions: list[BaseException] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        """Number of successful results."""
        return len(self.results)

    @property
    def error_count(self) -> int:
        """Number of failed tasks."""
        return len(self.exceptions)

    @property
    def total(self) -> int:
        """Total tasks (succeeded + failed)."""
        return self.success_count + self.error_count


def _execute(
    executor_type: type[ThreadPoolExecutor | ProcessPoolExecutor],
    func: Callable[..., Any],
    kwargs_list: Sequence[Mapping[str, Any]],
    max_workers: int | None,
    progress_tracker: int | None,
) -> ExecutorResults:
    """Shared core logic for both thread and process execution."""
    total_work = len(kwargs_list)

    with executor_type(max_workers=max_workers) as executor:
        futures = [executor.submit(func, **kwargs) for kwargs in kwargs_list]

    results: list[Any] = []
    exceptions: list[BaseException] = []

    for index, future in enumerate(futures, 1):
        exc = future.exception()
        if exc is not None:
            logger.error("%s raised %s", future, exc.__class__.__name__)
            exceptions.append(exc)
            continue

        results.append(future.result())

        if progress_tracker and index % progress_tracker == 0:
            logger.info("Progress: %d/%d", index, total_work)

    return ExecutorResults(results=results, exceptions=exceptions)


def parallelize_thread(
    func: Callable[..., Any],
    kwargs_list: Sequence[Mapping[str, Any]],
    max_workers: int | None = None,
    progress_tracker: int | None = None,
) -> ExecutorResults:
    """Run a function with multiple argument sets in parallel threads.

    Uses ThreadPoolExecutor (shared memory). Appropriate for I/O-bound
    work where the target function and its dependencies are thread-safe.

    Args:
        func: The function to call in parallel.
        kwargs_list: Sequence of dicts, each unpacked as **kwargs.
        max_workers: Maximum concurrent threads.
        progress_tracker: Log progress every N completed tasks.

    Returns:
        ExecutorResults with results (in order) and any exceptions.

    """
    return _execute(ThreadPoolExecutor, func, kwargs_list, max_workers, progress_tracker)


def parallelize_process(
    func: Callable[..., Any],
    kwargs_list: Sequence[Mapping[str, Any]],
    max_workers: int | None = None,
    progress_tracker: int | None = None,
) -> ExecutorResults:
    """Run a function with multiple argument sets in parallel processes.

    Uses ProcessPoolExecutor (separate memory per worker). Appropriate
    when the target function or its dependencies are NOT thread-safe
    (e.g., lxml/trafilatura HTML parsing). Each process gets its own
    memory space, so native-library thread-safety is irrelevant.

    Note: func and all arguments must be picklable (strings, dicts,
    lists — not open file handles, locks, or API client objects).

    Args:
        func: The function to call in parallel. Must be picklable.
        kwargs_list: Sequence of dicts, each unpacked as **kwargs. Must be picklable.
        max_workers: Maximum concurrent processes (capped at CPU count).
        progress_tracker: Log progress every N completed tasks.

    Returns:
        ExecutorResults with results (in order) and any exceptions.

    """
    cpus = cpu_count()
    if max_workers and max_workers > cpus:
        max_workers = cpus
    return _execute(ProcessPoolExecutor, func, kwargs_list, max_workers, progress_tracker)
