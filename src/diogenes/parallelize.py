"""Thread-based parallel execution with kwargs-style argument passing.

Wraps concurrent.futures.ThreadPoolExecutor with two features not
available in mainstream parallel libraries (joblib, tqdm, pqdm, MPIRE):

1. Native kwargs-style argument passing — accepts a sequence of dicts,
   each unpacked as **kwargs to the target function. Essential for
   calling functions with multiple named parameters (like sub-agent
   API calls with model, prompt, config, etc.).

2. Non-fatal error collection — collects exceptions alongside results
   rather than raising on first failure. The caller decides what to do
   with partial results. Essential for batch processing where partial
   success is expected (e.g., 12 of 13 evidence extractions succeed).

Origin: adapted from a shared collaboration between the project author
and Richie Cahill. Original source:
https://github.com/RichieCahill/dotfiles/blob/main/python/parallelize.py

Modifications for Diogenes:
- Removed ProcessPoolExecutor variant (all our work is I/O-bound)
- Removed early_error mode (not needed; use a for-loop if you want fail-fast)
- Simplified to a single public function
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
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


def parallelize_thread(
    func: Callable[..., Any],
    kwargs_list: Sequence[Mapping[str, Any]],
    max_workers: int | None = None,
    progress_tracker: int | None = None,
) -> ExecutorResults:
    """Run a function with multiple argument sets in parallel threads.

    Each entry in kwargs_list is unpacked as **kwargs to func. Results
    are collected in submission order; exceptions are collected separately
    rather than raising, so partial success is preserved.

    Args:
        func: The function to call in parallel.
        kwargs_list: Sequence of dicts, each unpacked as **kwargs.
        max_workers: Maximum concurrent threads (default: ThreadPoolExecutor default).
        progress_tracker: Log progress every N completed tasks (None to disable).

    Returns:
        ExecutorResults with results (in order) and any exceptions.

    """
    total_work = len(kwargs_list)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
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
