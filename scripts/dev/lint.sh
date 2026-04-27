#!/usr/bin/env bash
# lint.sh — run ruff check + ruff format --check, matching CI's unit-tests job.
#
# Container-local: this script assumes it is already running inside the
# dev container (invoked by st-validate-local, or directly via
# `st-docker-run -- scripts/dev/lint.sh`). It does not re-containerize.
set -euo pipefail

echo "== ruff check =="
uv run ruff check
echo "== ruff format --check =="
uv run ruff format --check .
