"""Progress logging for Diogenes CLI and pipeline.

Replaces ad-hoc ``print()`` calls with a configured :mod:`logging` setup:
an INFO-level logger named ``diogenes`` that fans out to a persistent
progress log file inside the run's instance directory, and — when stdout
is a terminal — also to stdout for interactive feedback.

Per-module callers stay simple:

    import logging

    logger = logging.getLogger(__name__)
    logger.info("Fetching sources...")

The module doing the logging has no idea whether output lands in a
terminal, a log file, or both. The handler setup in :func:`configure_progress_logger`
owns that decision, driven by the presence of a TTY at run start.

Two handlers, two formats:

- **File handler**: a small timestamp prefix (``HH:MM:SS``) so a persistent
  log can be read later without guessing at order or cadence. Always
  attached.
- **Stdout handler**: no prefix, matching the bare-print cadence that
  existed before this module. Only attached when :func:`sys.stdout.isatty`
  reports a terminal, so piped / backgrounded / CI invocations don't mix
  logging into pipeline output streams.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path  # noqa: TC003 — needed at runtime for path operations

_LOGGER_NAME = "diogenes"
_FILE_FORMAT = "%(asctime)s %(message)s"
_STDOUT_FORMAT = "%(message)s"
_TIME_FORMAT = "%H:%M:%S"


def configure_progress_logger(
    log_path: Path,
    *,
    tee_to_stdout: bool | None = None,
) -> logging.Logger:
    """Configure the Diogenes progress logger for a single run.

    Args:
        log_path: Where the persistent progress log should be written.
            Parent directory must already exist. Opened in append mode so
            a resumed run extends the file instead of truncating it.
        tee_to_stdout: If None (default), check :func:`sys.stdout.isatty`
            and mirror to stdout only when a terminal is present. Pass
            True or False to override (useful for tests and for
            ``--tee``-style CLI flags if ever added).

    Returns:
        The configured ``diogenes`` logger. Callers typically don't need
        this — ``logging.getLogger(__name__)`` on any ``diogenes.*``
        module propagates up to it.

    """
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    # Stop logs from bubbling to the root logger — that would double-print
    # in environments where root has a handler (pytest, ipython, etc.).
    logger.propagate = False
    # Idempotent setup: remove any handlers from a prior run in the same
    # process (e.g., two invocations inside one MCP server lifetime).
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()

    file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(_FILE_FORMAT, datefmt=_TIME_FORMAT))
    logger.addHandler(file_handler)

    if tee_to_stdout is None:
        tee_to_stdout = sys.stdout.isatty()

    if tee_to_stdout:
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setFormatter(logging.Formatter(_STDOUT_FORMAT))
        logger.addHandler(stdout_handler)

    return logger
