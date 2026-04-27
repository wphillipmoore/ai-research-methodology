#!/usr/bin/env bash
# test.sh — run pytest with branch coverage and 100% threshold, matching CI.
#
# CI runs `pytest --cov=diogenes --cov-report=term-missing --cov-branch
# --cov-fail-under=100` (see .github/workflows/ci.yml unit-tests job).
#
# Container-local: this script assumes it is already running inside the
# dev container (invoked by st-validate-local, or directly via
# `st-docker-run -- scripts/dev/test.sh`). It does not re-containerize.
set -euo pipefail

echo "== pytest --cov=diogenes --cov-branch --cov-fail-under=100 =="
uv run pytest --cov=diogenes --cov-report=term-missing --cov-branch --cov-fail-under=100
