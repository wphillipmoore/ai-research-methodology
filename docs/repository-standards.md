# AI Research Methodology Repository Standards

## Table of Contents

- [Pre-flight checklist](#pre-flight-checklist)
- [Local validation](#local-validation)
- [Linting policy](#linting-policy)
- [Python invocation](#python-invocation)
- [Tooling requirement](#tooling-requirement)
- [Merge strategy override](#merge-strategy-override)

## Pre-flight checklist

- Before modifying any files, check the current branch with `git status -sb`.
- If on `develop`, create a short-lived `feature/*` branch or ask for explicit approval to proceed on `develop`.
- If approval is granted to work on `develop`, call it out in the response and proceed only for that user-approved scope.
- Enable repository git hooks before committing: `git config core.hooksPath .githooks`.

## Local validation

- `st-validate-local`

## Linting policy

- Linter: `ruff`
- Rule set: `select = ["ALL"]` with scoped ignores per `pyproject.toml`
- Enforcement: CI and local validation
- Format: `ruff format` (double quotes, 120 char line length)

## Python invocation

- Always use `uv run` to invoke Python tools: `uv run pytest`, `uv run ruff`, `uv run mypy`.
- Never use `python3` directly outside of `uv run`.

## Tooling requirement

### Committing changes

```bash
st-commit \
  --type TYPE --message TEXT --agent AGENT \
  [--scope SCOPE] [--body BODY]
```

- `--type` (required): one of
  `feat|fix|docs|style|refactor|test|chore|ci|build`
- `--message` (required): commit description
- `--agent` (required): `claude` or `codex`
- `--scope` (optional): conventional commit scope
- `--body` (optional): detailed commit body

The script resolves the correct `Co-Authored-By` identity from
`standard-tooling.toml` and the git hooks validate the result.

### Submitting PRs

```bash
st-submit-pr \
  --issue NUMBER --summary TEXT \
  [--linkage KEYWORD] [--title TEXT] \
  [--notes TEXT] [--docs-only] [--dry-run]
```

- `--issue` (required): GitHub issue number (just the number)
- `--summary` (required): one-line PR summary
- `--linkage` (optional, default: `Fixes`):
  `Fixes|Closes|Resolves|Ref`
- `--title` (optional): PR title (default: most recent commit
  subject)
- `--notes` (optional): additional notes
- `--docs-only` (optional): applies docs-only testing exception
- `--dry-run` (optional): print generated PR without executing

The script detects the target branch and merge strategy
automatically.

## Merge strategy override

| Source branch | Target | Strategy |
|---------------|--------|----------|
| `feature/*`, `bugfix/*`, `chore/*`, `docs/*` | `develop` | Squash (`--squash`) |
| `release/*` | `main` | Regular merge (`--merge`) |
