# Validation

## Canonical local validation command

```bash
st-validate-local
```

This runs all Tier 1 validation checks: lint, format, type check, tests,
and repo-specific custom validation. Requires standard-tooling on PATH.

## Manual validation (without standard-tooling)

```bash
uv run ruff check
uv run ruff format --check .
uv run mypy src/
uv run pytest -v
```
