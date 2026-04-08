# Standard Tooling Integration Plan

## Goal

Configure the ai-research-methodology repo as a standard Python repo
in the same ecosystem as mq-rest-admin-python, consuming:

- **standard-tooling** — CLI tools, git hooks, dev scripts, Docker images
- **standard-actions** — GitHub Actions reusable workflows (CI, security, publish)
- **standards-and-conventions** — documentation standards, AI agent config

## What needs to be set up

### 1. GitHub Actions workflows

Clone from mq-rest-admin-python and adapt:

| Workflow | Source | Adaptations |
|----------|--------|-------------|
| ci.yml | mq-rest-admin-python | Remove MQ-specific integration tests, keep matrix + security |
| ci-push.yml | mq-rest-admin-python | Minimal changes — single Python, no security |
| publish.yml | mq-rest-admin-python | Change package name, remove MQ-specific gates |
| add-to-project.yml | mq-rest-admin-python | Update project ID |

### 2. Dev scripts (scripts/dev/)

Clone the standard pattern:

| Script | Purpose |
|--------|---------|
| test.sh | pytest via st-docker-test |
| lint.sh | ruff via st-docker-test |
| typecheck.sh | mypy via st-docker-test |
| audit.sh | pip-audit + pip-licenses via st-docker-test |
| validate_local_custom.sh | Repo-specific validation |
| validate_version.py | Semantic versioning policy |
| validate_changelog.py | Changelog validation |

### 3. Git hooks

```bash
git config core.hooksPath ../standard-tooling/scripts/lib/git-hooks
```

### 4. Repository standards docs

Create:
- docs/repository-standards.md (repository profile)
- docs/standards-and-conventions.md (canonical reference)
- docs/validation.md (canonical validation command)

Repository profile:
```yaml
repository_type: library
versioning_scheme: library
branching_model: library-release
release_model: artifact-publishing
primary_language: python
```

### 5. CLAUDE.md and AGENTS.md

Clone from mq-rest-admin-python, adapt for this repo:
- AI agent configuration
- Three-tier test documentation
- Standard-tooling setup instructions
- Memory policy

### 6. Changelog infrastructure

Add:
- cliff.toml (Keep a Changelog format)
- cliff-release-notes.toml (GitHub Release notes)

### 7. License compliance

Add:
- .pip-licenses-allowlist

### 8. uv lock file

Generate:
- uv.lock
- requirements.txt (exported)
- requirements-dev.txt (exported)

## Implementation order

1. Git hooks setup (immediate, local-only)
2. Dev scripts (enables Tier 1 local testing)
3. Repository standards docs (required by CI)
4. CLAUDE.md + AGENTS.md (AI agent config)
5. GitHub Actions workflows (enables Tier 2 + 3)
6. Changelog infrastructure
7. License compliance
8. uv lock file generation
9. publish.yml (when ready for PyPI)

## What stays unique to this repo

- The plugin directory (ai-research-methodology/)
- prompts/ directory
- docs/design/ (architecture docs)
- schemas/ (JSON schemas)
- templates/ (Jinja2)
- coordinator/ (Python coordinator)

These are layered ON TOP of the standard tooling infrastructure, not
replacements for it.
