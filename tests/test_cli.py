"""Tests for cli module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from diogenes.cli import _build_parser, main


class TestBuildParser:
    """Tests for _build_parser."""

    def test_run_subcommand(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["run", "input.json", "--output", "out/"])
        assert args.command == "run"
        assert args.input_file == "input.json"
        assert args.output == "out/"

    def test_rerun_subcommand(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["rerun", "--output", "/path/to/research"])
        assert args.command == "rerun"
        assert args.output == "/path/to/research"

    def test_resume_subcommand(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["resume", "/path/to/research/2026-04-22-120000"])
        assert args.command == "resume"
        assert args.instance_dir == "/path/to/research/2026-04-22-120000"

    def test_factcheck_subcommand(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["fact-check", "doc.md", "--output", "out/"])
        assert args.command == "fact-check"
        assert args.document == "doc.md"

    def test_render_subcommand(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["render", "/path/to/run", "--output", "md/"])
        assert args.command == "render"
        assert args.input_dir == "/path/to/run"

    def test_no_subcommand_fails(self) -> None:
        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])


class TestMain:
    """Tests for main function."""

    @patch("diogenes.commands.run.execute_rerun")
    @patch("diogenes.cli.argparse.ArgumentParser.parse_args")
    def test_rerun_delegates(self, mock_parse: MagicMock, mock_rerun: MagicMock) -> None:
        mock_parse.return_value = MagicMock(command="rerun", output="/dir")
        mock_rerun.return_value = 0
        assert main() == 0
        mock_rerun.assert_called_once_with("/dir")

    @patch("diogenes.commands.run.execute_resume")
    @patch("diogenes.cli.argparse.ArgumentParser.parse_args")
    def test_resume_delegates(self, mock_parse: MagicMock, mock_resume: MagicMock) -> None:
        mock_parse.return_value = MagicMock(command="resume", instance_dir="/dir/2026-04-22-120000")
        mock_resume.return_value = 0
        assert main() == 0
        mock_resume.assert_called_once_with("/dir/2026-04-22-120000")

    @patch("diogenes.cli.argparse.ArgumentParser.parse_args")
    def test_factcheck_not_implemented(self, mock_parse: MagicMock) -> None:
        mock_parse.return_value = MagicMock(command="fact-check", document="doc", output="out")
        assert main() == 1

    @patch("diogenes.cli.argparse.ArgumentParser.parse_args")
    def test_unknown_command(self, mock_parse: MagicMock) -> None:
        mock_parse.return_value = MagicMock(command="unknown")
        assert main() == 1

    @patch("diogenes.commands.run.execute")
    @patch("diogenes.cli.argparse.ArgumentParser.parse_args")
    def test_run_delegates(self, mock_parse: MagicMock, mock_execute: MagicMock) -> None:
        mock_parse.return_value = MagicMock(command="run", input_file="input.json", output="out/")
        mock_execute.return_value = 0
        assert main() == 0
        mock_execute.assert_called_once_with("input.json", "out/")

    @patch("diogenes.cli.argparse.ArgumentParser.parse_args")
    def test_render_dispatches(self, mock_parse: MagicMock, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        output_dir = tmp_path / "md"

        args = MagicMock(spec=["command", "input_dir", "output"])
        args.command = "render"
        args.input_dir = str(run_dir)
        args.output = str(output_dir)
        mock_parse.return_value = args

        with patch("diogenes.renderer.render_run") as mock_render:
            result = main()
        assert result == 0
        mock_render.assert_called_once()


class TestMainErrorSurfacing:
    """Content-asserting tests for the #154 fix.

    Before this fix, every pre-pipeline error path exited 1 with zero
    bytes on stderr because no logging handler was attached to the
    ``diogenes`` logger. Each test below triggers one concrete error
    branch and asserts that a specific, identifying substring appears on
    stderr — not just "something, anything".
    """

    def test_rerun_missing_output_dir_surfaces_error(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """dio rerun against a nonexistent --output prints a clear error."""
        missing = tmp_path / "does_not_exist"
        with patch("sys.argv", ["dio", "rerun", "--output", str(missing)]):
            rc = main()
        captured = capsys.readouterr()
        assert rc == 1
        assert "does not exist" in captured.err
        assert str(missing) in captured.err
        assert captured.err.strip() != ""

    def test_rerun_missing_source_input_surfaces_error(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """dio rerun against an empty dir names the missing source input."""
        output = tmp_path / "empty"
        output.mkdir()
        with patch("sys.argv", ["dio", "rerun", "--output", str(output)]):
            rc = main()
        captured = capsys.readouterr()
        assert rc == 1
        assert "Could not locate a single source input" in captured.err

    def test_run_missing_input_file_surfaces_error(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """dio run with a missing input file says so on stderr."""
        missing = tmp_path / "nonexistent.md"
        output = tmp_path / "out"
        with patch("sys.argv", ["dio", "run", str(missing), "--output", str(output)]):
            rc = main()
        captured = capsys.readouterr()
        assert rc == 1
        assert "Input file not found" in captured.err

    def test_run_nonempty_output_surfaces_error(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """dio run refuses a non-empty output dir with a specific message."""
        input_file = tmp_path / "input.json"
        input_file.write_text('{"claims": [], "queries": [{"text": "t"}]}')
        output = tmp_path / "output"
        output.mkdir()
        (output / "leftover").write_text("x")
        with patch("sys.argv", ["dio", "run", str(input_file), "--output", str(output)]):
            rc = main()
        captured = capsys.readouterr()
        assert rc == 1
        assert "already exists and is not empty" in captured.err
        # The helper message steering the user to `dio rerun` must also be visible.
        assert "dio rerun" in captured.err

    def test_resume_missing_instance_dir_surfaces_error(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """dio resume against a nonexistent instance dir says so on stderr."""
        missing = tmp_path / "nope"
        with patch("sys.argv", ["dio", "resume", str(missing)]):
            rc = main()
        captured = capsys.readouterr()
        assert rc == 1
        assert "does not exist" in captured.err
        assert str(missing) in captured.err

    def test_resume_missing_state_file_surfaces_error(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """dio resume on an instance dir without pipeline-state.json errors out."""
        instance = tmp_path / "instance"
        instance.mkdir()
        with patch("sys.argv", ["dio", "resume", str(instance)]):
            rc = main()
        captured = capsys.readouterr()
        assert rc == 1
        assert "pipeline-state.json" in captured.err

    def test_no_api_key_surfaces_error(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """dio rerun with no API key anywhere surfaces the exact config error.

        This is the original reproducer from issue #154: no API key, no
        .env, no .diorc, running `dio rerun` with an empty output dir.
        """
        # Strip every API-key source from the environment.
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        # Point HOME and CWD at tmp_path so config loader finds no
        # ~/.diorc, no ./.diorc, no ./.env.
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)

        output = tmp_path / "research"
        output.mkdir()
        # Seed a valid saved source input so we get past _find_saved_input.
        (output / "input.json").write_text('{"claims": [], "queries": [{"text": "t"}]}')

        with patch("sys.argv", ["dio", "rerun", "--output", str(output)]):
            rc = main()
        captured = capsys.readouterr()
        assert rc == 1
        assert "No API key found" in captured.err

    def test_argparse_unknown_subcommand_exits_nonzero(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """argparse's own error path already writes to stderr — make sure we don't regress it.

        Unlike the other branches, this one is handled by argparse before
        our dispatch fires. The stderr check here guards against a future
        refactor accidentally silencing argparse errors too.
        """
        with patch("sys.argv", ["dio", "bogus-subcommand"]), pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code != 0
        captured = capsys.readouterr()
        # argparse prints usage + "invalid choice" on stderr.
        assert captured.err.strip() != ""
