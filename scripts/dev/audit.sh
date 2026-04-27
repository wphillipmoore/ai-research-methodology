#!/usr/bin/env bash
# audit.sh — run uv lock + pip-audit + pip-licenses, matching CI.
#
# Container-local: this script assumes it is already running inside the
# dev container (invoked by st-validate-local, or directly via
# `st-docker-run -- scripts/dev/audit.sh`). It does not re-containerize.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "== uv lock --check =="
uv lock --check

echo "== pip-audit =="
uv run pip-audit -r requirements.txt -r requirements-dev.txt

echo "== pip-licenses =="
allow="$(grep -v '^#' "$repo_root/.pip-licenses-allowlist" | grep -v '^$' | paste -sd ';' -)"
uv run pip-licenses --allow-only="$allow"
