"""Shared pytest fixtures."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _reset_diogenes_logger() -> Iterator[None]:
    """Restore the ``diogenes`` logger to defaults between tests.

    ``configure_progress_logger`` sets ``propagate=False`` and attaches
    a FileHandler to ``diogenes``. If one test calls it and another test
    relies on pytest's ``caplog`` to capture records (which attaches at
    the root logger), the second test will see no output because the
    propagation chain was cut at ``diogenes``. Resetting after each test
    keeps logger state test-local.
    """
    yield
    logger = logging.getLogger("diogenes")
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logger.propagate = True
    logger.setLevel(logging.NOTSET)
