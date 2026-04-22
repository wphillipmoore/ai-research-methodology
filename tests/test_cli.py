"""Tests for cli module."""

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
    def test_render_dispatches(self, mock_parse: MagicMock, tmp_path: pytest.TempPathFactory) -> None:
        run_dir = tmp_path / "run"  # type: ignore[operator]
        run_dir.mkdir()
        output_dir = tmp_path / "md"  # type: ignore[operator]

        args = MagicMock(spec=["command", "input_dir", "output"])
        args.command = "render"
        args.input_dir = str(run_dir)
        args.output = str(output_dir)
        mock_parse.return_value = args

        with patch("diogenes.renderer.render_run") as mock_render:
            result = main()
        assert result == 0
        mock_render.assert_called_once()
