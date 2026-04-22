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
        assert args.runs == 3

    def test_run_with_runs(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["run", "input.json", "--output", "out/", "--runs", "5"])
        assert args.runs == 5

    def test_rerun_subcommand(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["rerun", "/path/to/research"])
        assert args.command == "rerun"
        assert args.research_dir == "/path/to/research"

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

    @patch("diogenes.cli.argparse.ArgumentParser.parse_args")
    def test_rerun_not_implemented(self, mock_parse: MagicMock) -> None:
        mock_parse.return_value = MagicMock(command="rerun", research_dir="/dir", runs=1)
        assert main() == 1

    @patch("diogenes.cli.argparse.ArgumentParser.parse_args")
    def test_factcheck_not_implemented(self, mock_parse: MagicMock) -> None:
        mock_parse.return_value = MagicMock(command="fact-check", document="doc", output="out", runs=1)
        assert main() == 1

    @patch("diogenes.cli.argparse.ArgumentParser.parse_args")
    def test_unknown_command(self, mock_parse: MagicMock) -> None:
        mock_parse.return_value = MagicMock(command="unknown")
        assert main() == 1

    @patch("diogenes.commands.run.execute")
    @patch("diogenes.cli.argparse.ArgumentParser.parse_args")
    def test_run_delegates(self, mock_parse: MagicMock, mock_execute: MagicMock) -> None:
        mock_parse.return_value = MagicMock(command="run", input_file="input.json", output="out/", runs=3)
        mock_execute.return_value = 0
        assert main() == 0
        mock_execute.assert_called_once_with("input.json", "out/", 3)

    @patch("diogenes.cli.argparse.ArgumentParser.parse_args")
    def test_render_single_run(self, mock_parse: MagicMock, tmp_path: pytest.TempPathFactory) -> None:
        # Create a "run" directory with no run-N subdirs
        run_dir = tmp_path / "run-1"  # type: ignore[operator]
        run_dir.mkdir()
        output_dir = tmp_path / "md"  # type: ignore[operator]

        # CLI render accesses args.input_file if hasattr, else args.input_dir
        # MagicMock auto-creates attributes, so use spec to control this
        args = MagicMock(spec=["command", "input_dir", "output"])
        args.command = "render"
        args.input_dir = str(run_dir)
        args.output = str(output_dir)
        mock_parse.return_value = args

        with patch("diogenes.renderer.render_run") as mock_render:
            result = main()
        assert result == 0
        mock_render.assert_called_once()

    @patch("diogenes.cli.argparse.ArgumentParser.parse_args")
    def test_render_run_group(self, mock_parse: MagicMock, tmp_path: pytest.TempPathFactory) -> None:
        # Create a run group directory with run-N subdirs
        group_dir = tmp_path / "group"  # type: ignore[operator]
        group_dir.mkdir()
        (group_dir / "run-1").mkdir()

        output_dir = tmp_path / "md"  # type: ignore[operator]
        args = MagicMock(spec=["command", "input_dir", "output"])
        args.command = "render"
        args.input_dir = str(group_dir)
        args.output = str(output_dir)
        mock_parse.return_value = args

        with patch("diogenes.renderer.render_run_group") as mock_render:
            result = main()
        assert result == 0
        mock_render.assert_called_once()
