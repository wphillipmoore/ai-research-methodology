#!/usr/bin/env bash
set -euo pipefail

export DOCKER_DEV_IMAGE="${DOCKER_DEV_IMAGE:-dev-python:3.14}"
export DOCKER_TEST_CMD="${DOCKER_TEST_CMD:-uv sync --check --frozen --group dev && uv lock --check && uv run pip-audit -r requirements.txt -r requirements-dev.txt && uv run pip-licenses --allow-only=\"\$(grep -v '^\#' .pip-licenses-allowlist | grep -v '^\$' | paste -sd ';' -)\"}"

if ! command -v st-docker-test >/dev/null 2>&1; then
  echo "ERROR: st-docker-test not found on PATH." >&2
  echo "Set up standard-tooling: export PATH=../standard-tooling/.venv/bin:\$PATH" >&2
  exit 1
fi
exec st-docker-test
