#!/usr/bin/env bash
# lint.sh — run ruff check + ruff format --check, matching CI's unit-tests job.
#
# Default: run on the host via `uv run` so failures surface immediately,
# without requiring Docker or `st-docker-test` on PATH. This mirrors the
# local-validation contract: anything CI rejects must be rejected locally.
#
# Opt-in Docker parity (for debugging CI-only failures):
#   USE_DOCKER=1 scripts/dev/lint.sh
set -euo pipefail

if [[ "${USE_DOCKER:-0}" == "1" ]]; then
  export DOCKER_DEV_IMAGE="${DOCKER_DEV_IMAGE:-dev-python:3.14}"
  export DOCKER_TEST_CMD="${DOCKER_TEST_CMD:-uv sync --frozen --group dev && uv run ruff check && uv run ruff format --check .}"

  if ! command -v st-docker-test >/dev/null 2>&1; then
    echo "ERROR: st-docker-test not found on PATH." >&2
    echo "Set up standard-tooling: export PATH=../standard-tooling/.venv/bin:\$PATH" >&2
    exit 1
  fi
  exec st-docker-test
fi

echo "== ruff check =="
uv run ruff check
echo "== ruff format --check =="
uv run ruff format --check .
