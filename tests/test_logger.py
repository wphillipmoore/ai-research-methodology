"""Tests for the progress logger setup."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from diogenes.logger import configure_progress_logger

if TYPE_CHECKING:
    import pytest


class TestConfigureProgressLogger:
    """Tests for configure_progress_logger."""

    def test_attaches_file_handler(self, tmp_path: pytest.TempPathFactory) -> None:
        log_path = tmp_path / "progress.log"  # type: ignore[operator]
        logger = configure_progress_logger(log_path, tee_to_stdout=False)
        # Exactly one handler (file); no stdout handler when tee disabled
        file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        stream_handlers = [
            h
            for h in logger.handlers
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        ]
        assert len(file_handlers) == 1
        assert len(stream_handlers) == 0

    def test_tee_adds_stdout_handler(self, tmp_path: pytest.TempPathFactory) -> None:
        log_path = tmp_path / "progress.log"  # type: ignore[operator]
        logger = configure_progress_logger(log_path, tee_to_stdout=True)
        stream_handlers = [
            h
            for h in logger.handlers
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        ]
        assert len(stream_handlers) == 1

    def test_writes_lines_to_file(self, tmp_path: pytest.TempPathFactory) -> None:
        log_path = tmp_path / "progress.log"  # type: ignore[operator]
        configure_progress_logger(log_path, tee_to_stdout=False)
        pipe_logger = logging.getLogger("diogenes.pipeline")
        pipe_logger.info("hello from a pipeline step")
        # Flush file handlers
        for h in logging.getLogger("diogenes").handlers:
            h.flush()
        content = log_path.read_text()
        assert "hello from a pipeline step" in content

    def test_reconfigure_is_idempotent(self, tmp_path: pytest.TempPathFactory) -> None:
        """Calling configure twice leaves exactly one FileHandler, not two."""
        log_path = tmp_path / "progress.log"  # type: ignore[operator]
        configure_progress_logger(log_path, tee_to_stdout=False)
        configure_progress_logger(log_path, tee_to_stdout=False)
        logger = logging.getLogger("diogenes")
        file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 1

    def test_auto_detect_tty_true(
        self,
        tmp_path: pytest.TempPathFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When tee_to_stdout is None and stdout is a TTY, stdout handler attaches."""
        fake_stdout = MagicMock()
        fake_stdout.isatty.return_value = True
        monkeypatch.setattr("diogenes.logger.sys.stdout", fake_stdout)

        log_path = tmp_path / "progress.log"  # type: ignore[operator]
        logger = configure_progress_logger(log_path)
        stream_handlers = [
            h
            for h in logger.handlers
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        ]
        assert len(stream_handlers) == 1

    def test_auto_detect_tty_false(
        self,
        tmp_path: pytest.TempPathFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When tee_to_stdout is None and stdout is not a TTY, no stdout handler."""
        fake_stdout = MagicMock()
        fake_stdout.isatty.return_value = False
        monkeypatch.setattr("diogenes.logger.sys.stdout", fake_stdout)

        log_path = tmp_path / "progress.log"  # type: ignore[operator]
        logger = configure_progress_logger(log_path)
        stream_handlers = [
            h
            for h in logger.handlers
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        ]
        assert len(stream_handlers) == 0
