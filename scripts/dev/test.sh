#!/usr/bin/env bash
# test.sh — run pytest with branch coverage and 100% threshold, matching CI.
#
# CI runs `pytest --cov=diogenes --cov-report=term-missing --cov-branch
# --cov-fail-under=100` (see .github/workflows/ci.yml unit-tests job).
#
# Default: run on the host via `uv run` so failures surface immediately.
# Opt-in Docker parity: USE_DOCKER=1 scripts/dev/test.sh
set -euo pipefail

if [[ "${USE_DOCKER:-0}" == "1" ]]; then
  export DOCKER_DEV_IMAGE="${DOCKER_DEV_IMAGE:-dev-python:3.14}"
  export DOCKER_TEST_CMD="${DOCKER_TEST_CMD:-uv sync --frozen --group dev && uv run pytest --cov=diogenes --cov-report=term-missing --cov-branch --cov-fail-under=100}"

  if ! command -v st-docker-test >/dev/null 2>&1; then
    echo "ERROR: st-docker-test not found on PATH." >&2
    echo "Set up standard-tooling: export PATH=../standard-tooling/.venv/bin:\$PATH" >&2
    exit 1
  fi
  exec st-docker-test
fi

echo "== pytest --cov=diogenes --cov-branch --cov-fail-under=100 =="
uv run pytest --cov=diogenes --cov-report=term-missing --cov-branch --cov-fail-under=100
