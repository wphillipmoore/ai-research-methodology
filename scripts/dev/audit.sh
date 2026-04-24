#!/usr/bin/env bash
# audit.sh — run uv lock + pip-audit + pip-licenses, matching CI.
#
# Default: run on the host via `uv run` so failures surface immediately.
# Opt-in Docker parity: USE_DOCKER=1 scripts/dev/audit.sh
set -euo pipefail

if [[ "${USE_DOCKER:-0}" == "1" ]]; then
  export DOCKER_DEV_IMAGE="${DOCKER_DEV_IMAGE:-dev-python:3.14}"
  export DOCKER_TEST_CMD="${DOCKER_TEST_CMD:-uv sync --check --frozen --group dev && uv lock --check && uv run pip-audit -r requirements.txt -r requirements-dev.txt && uv run pip-licenses --allow-only=\"\$(grep -v '^\#' .pip-licenses-allowlist | grep -v '^\$' | paste -sd ';' -)\"}"

  if ! command -v st-docker-test >/dev/null 2>&1; then
    echo "ERROR: st-docker-test not found on PATH." >&2
    echo "Set up standard-tooling: export PATH=../standard-tooling/.venv/bin:\$PATH" >&2
    exit 1
  fi
  exec st-docker-test
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "== uv lock --check =="
uv lock --check

echo "== pip-audit =="
uv run pip-audit -r requirements.txt -r requirements-dev.txt

echo "== pip-licenses =="
allow="$(grep -v '^#' "$repo_root/.pip-licenses-allowlist" | grep -v '^$' | paste -sd ';' -)"
uv run pip-licenses --allow-only="$allow"
