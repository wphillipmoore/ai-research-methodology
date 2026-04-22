# Execution Model

**Status:** Locked (baseline) — the three execution paths and the N-run
group semantics are a first-principles architectural decision. Adding a
fourth path, removing a path, or changing the run-group semantics
requires an explicit decision record and a spec update.
**Last verified:** 2026-04-22 (post-merge re-verification against the
CLI, state machine, MCP server, and `/research` skill after #110 / #93;
path consistency between CLI and skill is a tracked concern via issue
#102).
**Sources:** `project_multi_path_architecture`, `project_plugin_mcp_strategy`,
`project_search_architecture_decision`, `project_search_source_strategy`,
`project_batched_relevance_scoring`; implementation under
`src/diogenes/cli.py`, `src/diogenes/commands/run.py`,
`src/diogenes/state_machine.py`, `src/diogenes/mcp_server.py`,
`src/diogenes/pipeline.py`, and the `/research` skill in the plugin.

## Purpose

Diogenes can be invoked from three distinct execution environments — a
Python CLI, a Claude Code `/research` skill, and an MCP server consumed
by an AI coordinator. All three share the same sub-agent prompts and
JSON schemas, and MUST produce structurally identical JSON output for
the same input. This spec locks which paths exist, which components are
shared, what the run vs rerun semantics are, and what determinism
properties the system guarantees across retries and re-runs.

**Not in scope for this spec:** cross-instance synthesis or diff. The
pipeline produces one instance per invocation; comparison across
instances is a consumer concern (see
[`research-methodology.md`](research-methodology.md) R13 / R14a).

## Principle: prompts, schemas, and mechanics are shared; coordinators differ

The three paths are defined by how they **coordinate** calls, not by
what they call. Python mechanical components (search execution, page
fetch, JSON validation, result filtering, report rendering, cost
accounting) are a single implementation shared across all paths,
exposed via:

- direct Python import inside the CLI
- MCP tool calls inside the plugin `/research` skill
- MCP server endpoints for external coordinators

The AI judgment steps (input clarification, hypothesis generation,
search design, relevance scoring, source scoring, evidence
extraction, synthesis, assessment, self-audit) are all defined by the
same prompts under `src/diogenes/prompts/`, consumed verbatim by every
path.

## Supported execution paths

| Path | Coordinator | Mechanical layer | Billing model |
|------|-------------|------------------|---------------|
| CLI (`dio`) | Python coordinator (`pipeline.py`) | Python, in-process | Anthropic API, per-token |
| Plugin (`/research` skill) | AI coordinator inside Claude Code | MCP tool calls to `dio` | Claude Code (Max) subscription, flat-rate |
| MCP server (future / service) | External agentic coordinator | MCP tool calls to `dio` | Depends on coordinator |

## Requirements

### Path equivalence

- **R1.** Every supported execution path MUST use the same versioned
  prompts and JSON schemas for the same set of sub-agents.
- **R2.** For the same input, prompts, and schema versions, every
  path MUST produce JSON output that is **structurally identical**
  at the schema level (same fields, same validated values), allowing
  only for bound-identifier and timestamp differences (e.g., run IDs,
  wall-clock times, cache hit/miss annotations).
- **R3.** Markdown rendering of the JSON is a **separate** concern and
  MAY differ between paths. The JSON is the canonical artifact.

### Python mechanics, AI judgment

- **R4.** Mechanical operations — search execution against a provider,
  page fetch, content extraction, JSON validation, deduplication,
  sorting, filtering, reading-list generation, archival, rendering —
  MUST be implemented in Python and MUST be callable from every path
  (directly or via MCP). The AI layer MUST NOT re-implement them.
- **R5.** AI judgment steps (what to search, which results to include,
  how to score a source, which excerpts are evidence, how to
  synthesize findings) MUST be the only operations that consume
  model tokens. Model-driven mechanical operations (e.g., model-hosted
  web search) are a rejected approach on cost grounds
  (see `project_search_architecture_decision`).

### Search sources

- **R6.** The default search provider configuration MUST require no
  paid accounts (current baseline: Serper.dev free tier) so the
  methodology is usable without upfront cost.
- **R7.** The system SHOULD support curated academic providers
  (Google Scholar, arXiv, PubMed, Semantic Scholar) as additional
  tiers and SHOULD route searches to the providers appropriate for
  the hypothesis's evidence class.
- **R8.** The set of configured providers is user-controlled via
  configuration (`.diorc` and equivalents). Unconfigured providers
  referenced by a search plan MUST fall back to the default
  provider with the fallback logged in the run artifact (R8 here
  depends on `reliability-guarantees.md` R8).

### Research containers and instances

- **R9.** A `--output` directory is a **research container**: a parent
  directory holding one immutable source input file and one or more
  timestamped **instance** subdirectories (format
  `YYYY-MM-DD-HHMMSS/`). Each instance is the complete set of
  artifacts for one execution of the 11-step pipeline against the
  saved source input.
- **R10.** `dio run <input> --output <dir>` MUST refuse to execute
  against an existing non-empty `<dir>`. The error MUST direct the
  user to `dio rerun --output <dir>` instead. This preserves the
  invariant that `dio run` always establishes a **new** research
  definition from an explicit input file, and that a populated
  `<dir>` always represents an already-established definition.
- **R11.** `dio rerun --output <dir>` MUST locate exactly one regular
  file at the parent level (the source input copied by the prior
  `dio run`) and MUST execute the full 11-step pipeline against
  that file, including `step_01` re-clarification. Implicit
  reuse of a prior instance's clarified input is prohibited.
- **R12.** Timestamp collisions on instance-directory creation MUST
  be handled by bounded retry (current baseline: sleep 1s, up to
  3 attempts). Silent overwrite of a prior instance is prohibited.

### Parallelism

- **R13.** Parallelism inside an instance (e.g., scoring sources,
  extracting evidence) SHOULD default to threads. Process-based
  parallelism is acceptable only as a fallback for thread-unsafe
  dependencies, and such fallbacks MUST be tracked as tech debt
  with an open issue (see
  [`../tech-debt-register.md`](../tech-debt-register.md) TD-002).
- **R14.** Parallelism across instances is **not** a pipeline
  responsibility. A caller that wants N instances today invokes
  `dio rerun` N times. Adding pipeline-level cross-instance
  parallelism is out of scope for this spec; if reintroduced, it
  requires a new spec section rather than a revival of the removed
  N-run-group model (see
  [`parallelization.md`](parallelization.md) for intra-instance
  parallelism).

### Determinism and caching

- **R15.** The system MUST NOT silently substitute cached results.
  Cache hits MUST be recorded in the JSON output, per source, so a
  reader can tell whether a given scorecard was computed fresh or
  replayed from cache.
- **R16.** A single run MUST be tolerant of transient I/O failures
  via retries (R8 in `reliability-guarantees.md`); retries MUST be
  logged. Persistent failures MUST propagate as explicit skip
  dispositions, not as silent empty data.

### Cost accounting

- **R17.** Every run MUST record per-step token, model, and cost
  figures in the JSON artifact sufficient for downstream cost
  quantification and for comparing runs across paths and revisions.
- **R18.** The JSON-first architecture (see
  [`output-contract.md`](output-contract.md)) is motivated in part
  by cost: Markdown-as-inter-agent-exchange was measurably too
  expensive in tokens. Any proposal to re-introduce Markdown as an
  intermediate exchange format MUST quantify the token impact and
  be rejected if the cost increase is material.

## Non-goals

- Path-identical Markdown rendering. The drill-down hierarchy and flat
  file renderings are Python-implemented, but path-specific navigation
  metadata, breadcrumbs, or CSS wrappers MAY differ.
- Identical wall-clock performance across paths. The plugin path is
  expected to be slower per step but cheaper per-run.
- Zero-cost runs. The methodology prioritizes correctness; see
  [`reliability-guarantees.md`](reliability-guarantees.md) R18 /
  R19.

## Related specs

- [`research-methodology.md`](research-methodology.md) — top-level
  scope and supported modes
- [`reliability-guarantees.md`](reliability-guarantees.md) — contracts
  Python mechanics and AI judgment steps MUST satisfy
- [`output-contract.md`](output-contract.md) — what JSON artifacts
  must look like across paths
- [`workflow-architecture.md`](workflow-architecture.md) — the
  pipeline steps referenced above
- [`parallelization.md`](parallelization.md) (Draft) — intra-group
  parallelism
