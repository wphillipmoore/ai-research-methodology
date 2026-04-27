#!/usr/bin/env bash
# typecheck.sh — run mypy on src AND tests, matching CI's type-check job.
#
# CI runs `uv run mypy src tests` (see .github/workflows/ci.yml type-check job).
#
# Container-local: this script assumes it is already running inside the
# dev container (invoked by st-validate-local, or directly via
# `st-docker-run -- scripts/dev/typecheck.sh`). It does not re-containerize.
set -euo pipefail

echo "== mypy src tests =="
uv run mypy src tests
