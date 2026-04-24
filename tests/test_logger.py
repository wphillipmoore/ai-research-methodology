"""Tests for the progress logger setup."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from diogenes.logger import configure_cli_stderr_logger, configure_progress_logger

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


class TestConfigureProgressLogger:
    """Tests for configure_progress_logger."""

    def test_attaches_file_handler(self, tmp_path: Path) -> None:
        log_path = tmp_path / "progress.log"
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

    def test_tee_adds_stdout_handler(self, tmp_path: Path) -> None:
        log_path = tmp_path / "progress.log"
        logger = configure_progress_logger(log_path, tee_to_stdout=True)
        stream_handlers = [
            h
            for h in logger.handlers
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        ]
        assert len(stream_handlers) == 1

    def test_writes_lines_to_file(self, tmp_path: Path) -> None:
        log_path = tmp_path / "progress.log"
        configure_progress_logger(log_path, tee_to_stdout=False)
        pipe_logger = logging.getLogger("diogenes.pipeline")
        pipe_logger.info("hello from a pipeline step")
        # Flush file handlers
        for h in logging.getLogger("diogenes").handlers:
            h.flush()
        content = log_path.read_text()
        assert "hello from a pipeline step" in content

    def test_reconfigure_is_idempotent(self, tmp_path: Path) -> None:
        """Calling configure twice leaves exactly one FileHandler, not two."""
        log_path = tmp_path / "progress.log"
        configure_progress_logger(log_path, tee_to_stdout=False)
        configure_progress_logger(log_path, tee_to_stdout=False)
        logger = logging.getLogger("diogenes")
        file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 1

    def test_auto_detect_tty_true(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When tee_to_stdout is None and stdout is a TTY, stdout handler attaches."""
        fake_stdout = MagicMock()
        fake_stdout.isatty.return_value = True
        monkeypatch.setattr("diogenes.logger.sys.stdout", fake_stdout)

        log_path = tmp_path / "progress.log"
        logger = configure_progress_logger(log_path)
        stream_handlers = [
            h
            for h in logger.handlers
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        ]
        assert len(stream_handlers) == 1

    def test_auto_detect_tty_false(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When tee_to_stdout is None and stdout is not a TTY, no stdout handler."""
        fake_stdout = MagicMock()
        fake_stdout.isatty.return_value = False
        monkeypatch.setattr("diogenes.logger.sys.stdout", fake_stdout)

        log_path = tmp_path / "progress.log"
        logger = configure_progress_logger(log_path)
        stream_handlers = [
            h
            for h in logger.handlers
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        ]
        assert len(stream_handlers) == 0

    def test_preserves_cli_stderr_handler(self, tmp_path: Path) -> None:
        """CLI stderr handler survives a subsequent configure_progress_logger call.

        Regression guard for the #154 fix: if this ever breaks, in-pipeline
        errors would silently disappear on non-TTY invocations.
        """
        configure_cli_stderr_logger()
        logger = logging.getLogger("diogenes")
        stderr_before = [h for h in logger.handlers if getattr(h, "_diogenes_cli_stderr_handler", False)]
        assert len(stderr_before) == 1

        configure_progress_logger(tmp_path / "progress.log", tee_to_stdout=False)

        stderr_after = [h for h in logger.handlers if getattr(h, "_diogenes_cli_stderr_handler", False)]
        assert len(stderr_after) == 1
        assert stderr_after[0] is stderr_before[0]


class TestConfigureCliStderrLogger:
    """Tests for configure_cli_stderr_logger."""

    def test_attaches_stderr_handler(self) -> None:
        """A stderr StreamHandler is attached, flagged with the CLI sentinel."""
        configure_cli_stderr_logger()
        logger = logging.getLogger("diogenes")
        flagged = [h for h in logger.handlers if getattr(h, "_diogenes_cli_stderr_handler", False)]
        assert len(flagged) == 1
        assert isinstance(flagged[0], logging.StreamHandler)
        # Points at sys.stderr (the handler writes to whatever sys.stderr was
        # at the time of configure; we check the stream attribute).
        import sys

        assert flagged[0].stream is sys.stderr

    def test_idempotent(self) -> None:
        """Calling twice does not stack duplicate handlers."""
        configure_cli_stderr_logger()
        configure_cli_stderr_logger()
        logger = logging.getLogger("diogenes")
        flagged = [h for h in logger.handlers if getattr(h, "_diogenes_cli_stderr_handler", False)]
        assert len(flagged) == 1

    def test_info_level_messages_reach_stderr(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """logger.info() emits on stderr — the whole point of the CLI handler."""
        configure_cli_stderr_logger()
        logging.getLogger("diogenes.some.module").info("visible error text")
        captured = capsys.readouterr()
        assert "visible error text" in captured.err
        assert captured.out == ""

    def test_sets_info_level(self) -> None:
        """Logger level is INFO so info() records are not filtered out."""
        configure_cli_stderr_logger()
        assert logging.getLogger("diogenes").level == logging.INFO

    def test_skips_unrelated_handlers_and_attaches(self) -> None:
        """A pre-existing non-CLI handler does not short-circuit attachment.

        Exercises the loop branch where an existing handler is inspected,
        found not to carry the CLI sentinel, and the loop continues on
        to attach a fresh CLI stderr handler alongside it.
        """
        logger = logging.getLogger("diogenes")
        unrelated = logging.NullHandler()
        logger.addHandler(unrelated)

        configure_cli_stderr_logger()

        flagged = [h for h in logger.handlers if getattr(h, "_diogenes_cli_stderr_handler", False)]
        assert len(flagged) == 1
        # Unrelated handler remains attached — we only touch CLI handlers.
        assert unrelated in logger.handlers
