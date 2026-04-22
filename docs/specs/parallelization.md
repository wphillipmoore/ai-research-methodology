# Parallelization

**Status:** Locked (baseline) — the parallelization sprint merged in
#89 (`feat: parallel execution for evidence extraction via
parallelize_thread`) and #124 / #128 (`feat: process-parallelism for
fetches`). This spec describes the shipped intra-instance
parallelization model. Material changes — primitive default, scope
widening, or rate-limit policy — require a spec update before
implementation.
**Last verified:** 2026-04-22 (post-merge verification against
`src/diogenes/parallelize.py` (`parallelize_thread`,
`parallelize_process`, `ExecutorResults`) and `src/diogenes/pipeline.py`
call sites; tunable constants `_RELEVANCE_BATCH_SIZE = 5`,
`_RELEVANCE_THRESHOLD = 5`, `_SCORING_BATCH_SIZE = 1`,
`_MAX_SOURCES_TO_SCORE = 15` in `pipeline.py`).
**Sources:** `feedback_threads_over_processes`;
`src/diogenes/parallelize.py`, `src/diogenes/pipeline.py`, issues #89
(evidence-extraction parallelism), #124 (lxml/trafilatura thread-
unsafety), #128 (process-parallelism for fetches).

## Scope

This spec covers **intra-instance** parallelism — parallel work
inside one invocation of the 11-step pipeline. Cross-instance
parallelism is explicitly out of scope (see
[`execution-model.md`](execution-model.md) R14); there is no pipeline-
level coordination across `dio run` / `dio rerun` invocations today.

## Shipped model

- **Intra-step, across sources / items:**
  - `step_05` scoring — **serial** today (tech debt
    [`../tech-debt-register.md`](../tech-debt-register.md) TD-004).
  - `step_05` fetch — **process-parallel** via
    `parallelize_process` (`parallelize.py`). Process isolation is
    required because `lxml` / `trafilatura` are not thread-safe and
    contention produces native SIGABRT crashes; tracked as
    [`../tech-debt-register.md`](../tech-debt-register.md) TD-002.
  - `step_06` evidence extraction — **thread-parallel** via
    `parallelize_thread` (shipped in #89). Was the slowest step
    (~711.6s wall-clock) before parallelization.
- **Across steps within one instance:** strictly sequential;
  enforced by the `requires` list on each `StepDefinition` and by
  `PipelineState.next_step` in the state machine.
- **Across items (claims / queries / statements) within one
  instance:** strictly sequential inside each step.
- **Across instances:** no pipeline-level coordination; a user
  invokes `dio rerun` when they want another instance.

## Requirements

- **R1.** Threads MUST be the default parallelization primitive
  (`parallelize_thread`). Process-based parallelism
  (`parallelize_process`) is acceptable **only** where a
  dependency is known to be thread-unsafe; every such use MUST be
  paired with an entry in
  [`../tech-debt-register.md`](../tech-debt-register.md) and an
  open GitHub issue for migration to a thread-safe alternative
  (current: #124 / TD-002).
- **R2.** Parallel work MUST honor the reliability contracts in
  [`reliability-guarantees.md`](reliability-guarantees.md) — a
  failure in one parallel worker MUST NOT be silently swallowed,
  and MUST NOT be returned as an empty-but-valid result. Workers
  MUST return structured outcomes that the coordinator can
  distinguish "success with empty data" from "failure."
  `ExecutorResults` is the canonical shape used in
  `parallelize.py` for this.
- **R3.** Caching MUST remain correct under concurrency. If two
  parallel workers request the same source, one fresh computation
  (not two) MUST result; the second worker MUST observe the cache
  hit with the annotation required by
  [`output-contract.md`](output-contract.md) R19.
- **R4.** Parallelization MUST NOT break the search-accountability
  invariant (`len(selected) + len(rejected) == len(returned)`) or
  the source-accounting invariant (every fetched source appears
  in scored or skipped). A race condition that drops a result is
  a reliability bug, not a performance bug.
- **R5.** Every parallelized step MUST record per-worker outcomes
  in the pipeline artifacts — successes, failures, retries —
  such that a failed worker is visible in the instance's
  `pipeline-state.json` / `usage.json` / step output, per
  [`reliability-guarantees.md`](reliability-guarantees.md) R8.
- **R6.** Tunable concurrency / batching constants are currently
  module-level (`_RELEVANCE_BATCH_SIZE`, `_RELEVANCE_THRESHOLD`,
  `_SCORING_BATCH_SIZE`, `_MAX_SOURCES_TO_SCORE`). Moving these
  to configuration (issue #76) is a planned refinement and is
  non-breaking — until then, changing them requires a code change
  and re-verification against this spec.

## Non-goals

- Cross-instance parallelism at the pipeline level. See
  [`execution-model.md`](execution-model.md) R14.
- Parallelism inside synthesis (`step_07`), self-audit
  (`step_08`), or reporting (`step_09`) — these depend on the
  full upstream evidence and are intentionally sequential.
- Automatic fan-out across claims in `fact-check` mode. Items are
  processed sequentially inside each step; fan-out would require
  explicit design work and is not a parallelization-sprint goal.

## Related specs

- [`execution-model.md`](execution-model.md) — scope boundary
  (intra-instance vs cross-instance)
- [`reliability-guarantees.md`](reliability-guarantees.md) —
  invariants that must hold under concurrency
- [`output-contract.md`](output-contract.md) — how cache hits,
  retries, and failures surface in per-instance artifacts
- [`state-machine.md`](state-machine.md) — `per_source=True`
  declaration drives state-machine iteration for parallelizable
  steps
- [`../tech-debt-register.md`](../tech-debt-register.md) —
  TD-002 (process fallback for fetches), TD-004 (scorer serial)
