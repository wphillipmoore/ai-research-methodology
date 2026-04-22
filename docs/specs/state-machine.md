# State Machine

**Status:** Locked (baseline) — the state machine shipped in #110
(`feat: state-machine-driven pipeline orchestration`). Both CLI and
`/research` skill paths drive the same `PIPELINE_STEPS` registry. This
spec now describes the shipped system, not a target. Material changes
to the node set, node fields, or transition semantics require a spec
update before implementation.
**Last verified:** 2026-04-22 (post-merge verification against
`src/diogenes/state_machine.py` — `StepDefinition` dataclass, `PipelineState`
class, `PIPELINE_STEPS` list; and `src/diogenes/commands/run.py` —
`_dispatch_step`, `_run_pipeline`).
**Sources:** `src/diogenes/state_machine.py` (`StepDefinition`,
`PipelineState`, `PIPELINE_STEPS`), `src/diogenes/commands/run.py`
(`_dispatch_step`, `_run_pipeline`), `src/diogenes/mcp_server.py`
(`dio_next_step`, `dio_execute_step`); `project_show_your_work_principle`
for the deterministic-post-condition requirement;
`feedback_failure_must_not_be_silent` for node failure semantics.

## Purpose

The 11-step pipeline is orchestrated by an explicit state machine in
`src/diogenes/state_machine.py`. Both the CLI path (`dio run` /
`dio rerun`) and the `/research` skill path iterate the same
`PIPELINE_STEPS` registry, diverging only at the execution layer
(direct Python handler calls for CLI; `dio_next_step` /
`dio_execute_step` MCP tools for the skill). Each node (step) owns:

- the prompt for that step (if `category` is `llm` or `hybrid`);
- the input and output JSON schemas for that step;
- the deterministic Python post-condition checks for that step's output
  (see [`reliability-guarantees.md`](reliability-guarantees.md) R1);
- the failure / retry / skip semantics for that step;
- the tests that exercise that step in isolation.

The state-machine representation makes the pipeline's transition and
failure behavior legible to pushback, alignment, and agentic-review,
and makes per-step iteration (the primary activity of prompt tuning)
cheaper — prompt, schema, post-conditions, and tests for a node can
change without touching the coordinator.

## `StepDefinition` fields (shipped)

Every node in `PIPELINE_STEPS` is a `StepDefinition` with the
following fields (declared in `state_machine.py`):

| Field | Purpose |
|-------|---------|
| `name` | Unique step identifier (e.g., `step_06_evidence_packets`) |
| `display_name` | Human-readable name for progress output |
| `output_file` | JSON artifact this step produces, or `None` for in-place mutations |
| `category` | One of `llm`, `python_only`, `hybrid` — determines execution path |
| `requires` | List of prior output files that must exist before this step can run |
| `schema` | Output schema filename — used for both constrained decoding (CLI) and post-hoc validation (skill) |
| `prompt` | Compiled sub-agent prompt filename (`None` for `python_only`) |
| `python_handler` | Name of the `pipeline.py` function to call; used by CLI and by `dio_execute_step` for Python-only steps |
| `post_validators` | Validator names run after step completion (e.g., `validate_packets`) |
| `mcp_tools` | MCP tools the agent needs for this step (e.g., `dio_fetch`) |
| `per_source` | If `True`, step runs once per source; the state machine handles iteration |

The `PipelineState` class tracks per-step status via
`pipeline-state.json` with `started_at`, `completed_at`, and
`elapsed_seconds` timestamps, bracketed by `mark_started` /
`mark_complete` calls around each step.

## Node inventory (shipped)

Derived from `PIPELINE_STEPS` in `state_machine.py`. See
[`workflow-architecture.md`](workflow-architecture.md) for per-step
notes and parallelism/caching behavior.

| # | Node (`name`) | Category | Output file | Requires |
|---|---------------|----------|-------------|----------|
| 1 | `step_01_research_input_clarified` | llm | `research-input-clarified.json` | — |
| 2 | `step_02_hypotheses` | llm | `hypotheses.json` | `research-input-clarified.json` |
| 3 | `step_03_search_plans` | llm | `search-plans.json` | `research-input-clarified.json`, `hypotheses.json` |
| 4 | `step_04_search_results` | hybrid | `search-results.json` | prior outputs + MCP `dio_search` / `dio_search_batch` |
| 5 | `step_05_scorecards` | hybrid | `source-scorecards.json` | prior outputs + MCP `dio_fetch` |
| 6 | `step_06_evidence_packets` | llm | `evidence-packets.json` | `source-scorecards.json`; `per_source=True`, parallel via `parallelize_thread` |
| 7 | `step_07_synthesis` | llm | `synthesis.json` | `evidence-packets.json` |
| 8 | `step_08_self_audit` | llm | `self-audit.json` | `synthesis.json` |
| 9 | `step_09_reports` | llm | `report.json` | `self-audit.json` |
| 10 | `step_10_archive` | python_only | — | all prior outputs |
| 11 | `step_11_pipeline_events` | python_only | — | reconciles events into `pipeline-state.json` |

Clean sequential numbering `step_01` through `step_11` is an
intentional invariant — no gaps, no sub-steps (no legacy `5b` / `678`
/ `9b` naming). Adding a step between existing ones requires
renumbering and is a spec-update event.

## Requirements

- **R1.** Every node MUST be expressible as a `StepDefinition` record
  with prompt, schema, Python handler, post-validators, MCP tools,
  and `requires` list declared in one place. Splitting a step's
  contract across unrelated modules is prohibited.
- **R2.** The `llm`, `python_only`, and `hybrid` node categories MUST
  each be first-class at the coordinator level. A `python_only`
  node MUST NOT require the coordinator to invoke an LLM; a
  `hybrid` node MUST explicitly declare its MCP tool needs so the
  skill coordinator can grant them.
- **R3.** Transitions between nodes MUST be deterministic and driven
  by the `requires` list in `StepDefinition`. The coordinator MUST
  NOT infer the next node from prompt output. `PipelineState.next_step`
  is the canonical next-step oracle.
- **R4.** Per-source iteration MUST be handled by the state machine
  itself (`per_source=True` on the `StepDefinition`), not by
  duplicating nodes or by having the step handler do its own
  iteration.
- **R5.** Every node MUST declare and honor its failure semantics —
  which failures abort the instance, which skip an item with a
  logged skip disposition, and which retry. The coordinator MUST
  apply those declarations uniformly across CLI and skill paths
  (see [`execution-model.md`](execution-model.md) R1 / R2).
- **R6.** The `/research` skill and the CLI path MUST drive the
  **same** `PIPELINE_STEPS` registry. Divergent prompts,
  post-conditions, or failure handling between paths is a
  violation; it would also break
  [`execution-model.md`](execution-model.md) R1 / R2.
- **R7.** Each node MUST be independently testable. The test suite
  for a node exercises the pre-condition (input schema), the prompt
  (if applicable, with stubbed model), the post-condition (Python
  validator), and the failure-semantics declaration.
- **R8.** Clean sequential step numbering (`step_01` … `step_11`)
  MUST be preserved. Adding, removing, or re-ordering a step is a
  breaking change to the state machine and requires a spec update
  and a corresponding migration for any consumer that hard-codes
  step names.
- **R9.** `PipelineState` MUST be serializable to
  `pipeline-state.json` per instance, capturing per-step
  `started_at` / `completed_at` / `elapsed_seconds` at minimum, so
  that reruns can be audited for timing drift across instances.

## Related specs

- [`workflow-architecture.md`](workflow-architecture.md) — the step
  map this state machine encodes
- [`execution-model.md`](execution-model.md) — path-equivalence
  requirement that the state machine enforces
- [`reliability-guarantees.md`](reliability-guarantees.md) — the
  post-condition and failure-semantics contracts every node MUST
  satisfy
- [`output-contract.md`](output-contract.md) — methodology snapshot
  and per-step accounting fields the nodes must produce
- [`../tech-debt-register.md`](../tech-debt-register.md) —
  TD-003 (monolithic SKILL.md), the deviation this spec describes
  the fix for
