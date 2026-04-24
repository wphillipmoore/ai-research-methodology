#!/usr/bin/env bash
# typecheck.sh — run mypy on src AND tests, matching CI's type-check job.
#
# CI runs `uv run mypy src tests` (see .github/workflows/ci.yml type-check job).
# Historically this script ran `mypy src/` only, which let tests-only type
# errors escape local validation. Now it mirrors CI.
#
# Default: run on the host via `uv run` so failures surface immediately.
# Opt-in Docker parity: USE_DOCKER=1 scripts/dev/typecheck.sh
set -euo pipefail

if [[ "${USE_DOCKER:-0}" == "1" ]]; then
  export DOCKER_DEV_IMAGE="${DOCKER_DEV_IMAGE:-dev-python:3.14}"
  export DOCKER_TEST_CMD="${DOCKER_TEST_CMD:-uv sync --frozen --group dev && uv run mypy src tests}"

  if ! command -v st-docker-test >/dev/null 2>&1; then
    echo "ERROR: st-docker-test not found on PATH." >&2
    echo "Set up standard-tooling: export PATH=../standard-tooling/.venv/bin:\$PATH" >&2
    exit 1
  fi
  exec st-docker-test
fi

echo "== mypy src tests =="
uv run mypy src tests
