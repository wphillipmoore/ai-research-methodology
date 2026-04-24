"""Diogenes CLI — entry point for the dio command.

Usage:
    dio run <input-file> --output <dir>
    dio rerun --output <dir>
    dio resume <instance-dir>
    dio fact-check <document> --output <dir>
    dio render <run-dir> --output <dir>
"""

from __future__ import annotations

import argparse
import sys

from diogenes.logger import configure_cli_stderr_logger


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="dio",
        description="Diogenes — deterministic AI research coordinator",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- dio run ---
    run_parser = subparsers.add_parser(
        "run",
        help="Execute new research from an input file",
    )
    run_parser.add_argument(
        "input_file",
        help="Path to input file (JSON or markdown with claims/queries/axioms)",
    )
    run_parser.add_argument(
        "--output",
        required=True,
        help="Output directory for research results (must be fresh — one run per directory)",
    )

    # --- dio rerun ---
    rerun_parser = subparsers.add_parser(
        "rerun",
        help="Run a new instance of existing research (uses the saved source input)",
    )
    rerun_parser.add_argument(
        "--output",
        required=True,
        help="Parent output directory previously populated by 'dio run'",
    )

    # --- dio resume ---
    resume_parser = subparsers.add_parser(
        "resume",
        help="Finish a previously interrupted instance from where it left off",
    )
    resume_parser.add_argument(
        "instance_dir",
        help="Path to the timestamped instance directory to resume",
    )

    # --- dio fact-check ---
    factcheck_parser = subparsers.add_parser(
        "fact-check",
        help="Extract claims from a document and verify them",
    )
    factcheck_parser.add_argument(
        "document",
        help="Path or URL to document to fact-check",
    )
    factcheck_parser.add_argument(
        "--output",
        required=True,
        help="Output directory for research results (must be fresh — one run per directory)",
    )

    # --- dio render ---
    render_parser = subparsers.add_parser(
        "render",
        help="Render a JSON research output directory to linked markdown",
    )
    render_parser.add_argument(
        "input_dir",
        help="Path to a run directory (containing JSON step outputs)",
    )
    render_parser.add_argument(
        "--output",
        required=True,
        help="Output directory for rendered markdown tree",
    )

    return parser


def main() -> int:
    """Entry point for the dio/diogenes CLI."""
    # Attach a stderr handler to the diogenes logger BEFORE dispatch so every
    # ``logger.info("ERROR: ...")`` in the pre-pipeline / pipeline code
    # surfaces to the caller. Without this, any failure before
    # configure_progress_logger() runs (missing API key, missing input,
    # non-empty --output, etc.) exits 1 with zero bytes on stderr. See #154.
    configure_cli_stderr_logger()

    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "run":
        from diogenes.commands.run import execute as run_execute

        return run_execute(args.input_file, args.output)

    if args.command == "rerun":
        from diogenes.commands.run import execute_rerun

        return execute_rerun(args.output)

    if args.command == "resume":
        from diogenes.commands.run import execute_resume

        return execute_resume(args.instance_dir)

    if args.command == "fact-check":
        print(f"dio fact-check: doc={args.document} output={args.output}")
        print("Not yet implemented.")
        return 1

    if args.command == "render":
        from pathlib import Path

        from diogenes.renderer import render_run

        input_path = Path(args.input_dir)
        output_path = Path(args.output)

        print(f"Rendering run: {input_path}")
        render_run(input_path, output_path)

        print(f"Rendered to: {output_path}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
