# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working
with code in this repository.

## Standards References

This repository follows documented standards. Do NOT attempt to load and
memorize these at session start. Consult them on demand when the work
requires it.

- **Repository-specific standards**: `docs/repository-standards.md` —
  pre-flight checklist, branching, merge strategy, commit format, AI
  co-authors, linting policy
- **Canonical standards**: `../standards-and-conventions` (local) or
  https://github.com/wphillipmoore/standards-and-conventions (remote)

Read these documents when:
- Setting up the development environment
- Making decisions about branching, merging, or releasing
- Unsure about commit message format or PR conventions
- Validating repository structure or compliance

## Memory policy

Memory is available but scoped. Only use project memory for information
that is **exclusive to this repository's product**.

**Use memory for:**
- Design decisions about the AI Research Methodology (architecture,
  JSON schemas, sub-agent design, workflow choices)
- User preferences for working in this repo
- Project status and planning context for future sessions

**Do NOT use memory for:**
- Workarounds for standard-tooling, standard-actions, or GitHub Actions
  (those go in the tooling repo's docs or issues)
- Behavioral corrections that should apply across all repos (those go
  in standards-and-conventions or shared CLAUDE.md patterns)
- Fixes for cross-repo tools (git hooks, CI workflows, Docker images)

**The test:** Would this memory entry be wrong or misleading if applied
in a different repository? If yes, it does not belong in memory — it
belongs in shared documentation.

## Parallel AI agent development

This repository supports running multiple Claude Code agents in parallel via
git worktrees. The convention keeps parallel agents' working trees isolated
while preserving shared project memory (which Claude Code derives from the
session's starting CWD).

**Canonical spec:**
[`standard-tooling/docs/specs/worktree-convention.md`](https://github.com/wphillipmoore/standard-tooling/blob/develop/docs/specs/worktree-convention.md)
— full rationale, trust model, failure modes, and memory-path implications.
The canonical text lives in `standard-tooling`; this section is the local
on-ramp.

### Structure

```text
~/dev/github/ai-research-methodology/     ← sessions ALWAYS start here
  .git/
  CLAUDE.md, src/, docs/, …               ← main worktree (usually `develop`)
  .worktrees/                             ← container for parallel worktrees
    issue-150-adopt-worktree-convention/  ← worktree on feature/150-...
    …
```

### Rules

1. **Sessions always start at the project root.**
   `cd ~/dev/github/ai-research-methodology && claude` — never from inside
   `.worktrees/<name>/`. This keeps the memory-path slug stable and shared.
2. **Each parallel agent is assigned exactly one worktree.** The session
   prompt names the worktree (see Agent prompt contract below).
   - For Read / Edit / Write tools: use the worktree's absolute path.
   - For Bash commands that touch files: `cd` into the worktree first,
     or use absolute paths.
3. **The main worktree is read-only.** All edits flow through a worktree
   on a feature branch — the logical endpoint of the standing
   "no direct commits to `develop`" policy.
4. **One worktree per issue.** Don't stack in-flight issues. When a
   branch lands, remove the worktree before starting the next.
5. **Naming: `issue-<N>-<short-slug>`.** `<N>` is the GitHub issue
   number; `<short-slug>` is 2–4 kebab-case tokens.

### Agent prompt contract

When launching a parallel-agent session, use this template (fill in the
placeholders):

```text
You are working on issue #<N>: <issue title>.

Your worktree is: /Users/pmoore/dev/github/ai-research-methodology/.worktrees/issue-<N>-<slug>/
Your branch is:   feature/<N>-<slug>

Rules for this session:
- Do all git operations from inside your worktree:
    cd <absolute-worktree-path> && git <command>
- For Read / Edit / Write tools, use the absolute worktree path.
- For Bash commands that touch files, cd into the worktree first
  or use absolute paths.
- Do not edit files at the project root. The main worktree is
  read-only — all changes flow through your worktree on your
  feature branch.
```

All fields are required.

## Project Overview

`ai-research-methodology` is a unified research methodology for AI agents
combining nine intelligence and scientific frameworks into an evidence-based
process. It is available as a Claude Code plugin, a Python coordinator for
API-driven research, and a standalone prompt for any AI interface.

The repository contains:
- **Plugin** (`ai-research-methodology/`): Claude Code plugin with `/research` skill
- **Prompts** (`prompts/`): Shared prompt files for sub-agents (used by both plugin and Python)
- **Schemas** (`docs/design/schemas/`): JSON Schema definitions for data interchange
- **Coordinator** (`coordinator/`): Python coordinator for API-driven orchestration (WIP)
- **Templates** (`templates/`): Jinja2 templates for markdown output rendering (WIP)
- **Tests** (`tests/`): pytest test suite
- **Design docs** (`docs/design/`): Architecture, workflow, and schema documentation

**Status**: Pre-Alpha (plugin is functional; Python coordinator is in design)

**Canonical Standards**: This repository follows standards at
https://github.com/wphillipmoore/standards-and-conventions
(local path: `../standards-and-conventions` if available)

## Development Commands

### Standard Tooling

```bash
git config core.hooksPath ../standard-tooling/scripts/lib/git-hooks  # Enable git hooks
```

Standard-tooling CLI tools (`st-commit`, `st-validate-local`, etc.) are
pre-installed in the dev container images. No local setup required.

### Environment Setup

```bash
# Install dependencies and sync environment
uv sync --group dev
```

### Three-Tier CI Model

Testing is split across three tiers with increasing scope and cost:

**Tier 1 — Local pre-commit (seconds):** Fast smoke tests in a single
container. Run before every commit.

```bash
./scripts/dev/test.sh        # Unit tests in dev-python:3.14
./scripts/dev/lint.sh        # Ruff check + format in dev-python:3.14
./scripts/dev/typecheck.sh   # mypy in dev-python:3.14
./scripts/dev/audit.sh       # pip-audit in dev-python:3.14
```

**Tier 2 — Push CI (~3-5 min):** Triggers automatically on push to
`feature/**`, `bugfix/**`, `hotfix/**`, `chore/**`. Single Python version
(3.14), no security scanners or release gates.

**Tier 3 — PR CI (~8-10 min):** Triggers on `pull_request`. Full Python
matrix (3.12, 3.13, 3.14), security scanners (CodeQL, Trivy, Semgrep),
standards compliance, and release gates.

### Validation

```bash
# Quick local validation (without standard-tooling)
uv run ruff check
uv run ruff format --check .
uv run mypy src/
uv run pytest -v
```

### Testing

```bash
# Run tests
uv run pytest -v

# Run tests with coverage
uv run pytest --cov=ai_research_methodology --cov-report=term-missing --cov-branch

# Run integration tests (requires ANTHROPIC_API_KEY)
AI_RESEARCH_RUN_INTEGRATION=1 uv run pytest -m integration
```

### Linting and Formatting

```bash
# Run Ruff linter
uv run ruff check

# Run Ruff formatter (check only)
uv run ruff format --check .

# Run Ruff formatter (fix)
uv run ruff format .

# Run mypy type checker
uv run mypy src/
```

## Architecture

### Dual Interface

The research methodology is available through two interfaces:

1. **Claude Code Plugin** (`ai-research-methodology/`): Interactive use
   via `/research run`, `/research fact-check`, etc. The plugin's SKILL.md
   orchestrates research within a Claude Code session.

2. **Python Coordinator** (`coordinator/`): Programmatic use via API.
   The coordinator reads shared prompts, calls AI sub-agents via the
   Anthropic API, manages parallelism, and renders output from JSON
   templates.

Both interfaces use the same shared prompt files (`prompts/`).

### Sub-Agent Architecture

Each research step is a focused AI sub-agent with:
- A shared prompt file (`prompts/sub-agents/*.md`)
- An input JSON schema
- An output JSON schema
- A standard preamble for input handling (JSON preferred, text fallback)

See `docs/design/workflow-architecture.md` for the full workflow chart
and sub-agent definitions.

### Key Design Principles

1. **JSON is the canonical data format.** Markdown is a rendering.
2. **Every sub-agent: JSON in, JSON out.** Validate before processing.
3. **The prompt is the deliverable.** Invocation path is plumbing.
4. **Python handles deterministic work.** AI handles analytical work.
5. **Correctness before cost.** Make it right, then make it fast.

## Key References

- `docs/design/workflow-architecture.md` — Full workflow chart
- `docs/design/sub-agent-preamble.md` — Standard sub-agent input handling
- `docs/design/schemas/` — JSON Schema definitions
- `docs/design/tooling-integration.md` — Standard tooling integration plan
