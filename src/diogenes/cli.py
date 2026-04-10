"""Diogenes CLI — entry point for the dio command.

Usage:
    dio run <input-file> --output <dir> [--runs N]
    dio rerun <research-dir> [--runs N]
    dio fact-check <document> --output <dir> [--runs N]
"""

from __future__ import annotations

import argparse
import sys


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
        help="Output directory for research results",
    )
    run_parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Number of independent runs (default: 3)",
    )

    # --- dio rerun ---
    rerun_parser = subparsers.add_parser(
        "rerun",
        help="Re-execute previous research from saved input",
    )
    rerun_parser.add_argument(
        "research_dir",
        help="Path to existing research instance directory",
    )
    rerun_parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Number of independent runs (default: 3)",
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
        help="Output directory for research results",
    )
    factcheck_parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Number of independent runs (default: 3)",
    )

    return parser


def main() -> int:
    """Entry point for the dio/diogenes CLI."""
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "run":
        print(f"dio run: input={args.input_file} output={args.output} runs={args.runs}")
        print("Not yet implemented.")
        return 1

    if args.command == "rerun":
        print(f"dio rerun: dir={args.research_dir} runs={args.runs}")
        print("Not yet implemented.")
        return 1

    if args.command == "fact-check":
        print(f"dio fact-check: doc={args.document} output={args.output} runs={args.runs}")
        print("Not yet implemented.")
        return 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
