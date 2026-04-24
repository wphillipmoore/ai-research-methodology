# Validation

## Canonical local validation command

```bash
st-validate-local
```

This runs all Tier 1 validation checks: lint, format, type check, tests,
and repo-specific custom validation. Requires standard-tooling on PATH.

The dev scripts (`scripts/dev/lint.sh`, `typecheck.sh`, `test.sh`,
`audit.sh`) run **on the host** via `uv run` by default, so failures
surface without needing Docker. This is the intentional local-validation
contract: anything CI rejects must be rejected locally.

For CI parity (to reproduce a container-only failure), opt in with:

```bash
USE_DOCKER=1 scripts/dev/lint.sh
```

This requires `st-docker-test` on PATH and the Docker daemon running.

## What each script runs (must match CI)

- `lint.sh` runs `uv run ruff check` and `uv run ruff format --check .`
  (matches CI unit-tests: Run ruff check + Run ruff format check).
- `typecheck.sh` runs `uv run mypy src tests` (matches CI type-check).
- `test.sh` runs `uv run pytest --cov=diogenes --cov-branch
  --cov-fail-under=100` (matches CI unit-tests: Run tests with coverage).
- `audit.sh` runs `uv lock --check`, `uv run pip-audit`, and
  `uv run pip-licenses` (matches CI dependency-audit).

## Manual validation (without standard-tooling)

```bash
uv run ruff check
uv run ruff format --check .
uv run mypy src tests
uv run pytest --cov=diogenes --cov-branch --cov-fail-under=100
```
