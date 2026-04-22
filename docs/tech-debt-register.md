# Tech-Debt Register

**Status:** Living document — entries are added, updated, and retired as
work progresses. Entries here are **accepted** deviations: the team
knows about them, chose to accept them for specific reasons, and has a
direction (or an issue) tracking the strategic fix.
**Last reviewed:** 2026-04-22 (post-merge pass: TD-003 resolved by #110 /
PR #119; TD-002 and TD-004 re-verified as still Active).
**Scope:** `ai-research-methodology` (Diogenes). Not a spec — this file
is bookkeeping, not intent. Specs live under [`specs/`](specs/).

## How to use this file

- **Pushback / alignment** should consult this register when reviewing a
  spec or plan. A proposal that re-introduces an accepted deviation, or
  that contradicts the stated strategic direction for one, should be
  flagged.
- **Agentic review** should flag code changes that deepen an active
  tech-debt entry without a note acknowledging it.
- **When an entry is resolved**, move its status to `Resolved`, record
  the resolving commit/PR/issue, and leave it in the register for
  historical reference. Rewrite history only by marking entries
  `Obsolete` (with reason) — do not delete them.
- **New entries** follow the schema below. ID is monotonically
  increasing (TD-NNN); entries are listed newest-first.

## Entry schema

```markdown
## TD-NNN — <short summary>

**Status:** Active | Resolved | Obsolete
**Accepted:** YYYY-MM-DD
**Tracking issue:** #NNN (or `—` if untracked)
**Affects:** <module / subsystem / spec requirement this deviates from>

**What we accepted:**
<Concrete description of the tactical decision — the hack, the workaround,
the shortcut, the deferred refactor.>

**Why we accepted it:**
<The constraint, deadline, dependency, or tradeoff that justified the
deviation at the time. Keep this honest — future-us needs to judge
whether the justification still applies.>

**Strategic fix direction:**
<What "right" looks like. Not necessarily a committed plan, but enough
for pushback and alignment to recognize when new work is pointed the
wrong way.>

**Resolution (when applicable):**
<Commit, PR, or issue that resolved the deviation; move Status to
Resolved, leave the rest intact for history.>
```

## Active entries

## TD-004 — Scorer runs at `batch_size = 1` without parallelized scorer calls

**Status:** Active
**Accepted:** 2026-04-22 (retroactively recorded)
**Tracking issue:** — (to be filed as part of the 2.0 runway)
**Affects:** `src/diogenes/pipeline.py` (`_SCORING_BATCH_SIZE = 1`); execution
model [`execution-model.md`](specs/execution-model.md) R13.

**What we accepted:**
Source scoring currently runs one source at a time. The tunable
`_SCORING_BATCH_SIZE` is set to 1, and per-source scorer calls are not
parallelized across sources within a single run. Real-world runs scale
linearly in source count at this step.

**Why we accepted it:**
Shipping the full 11-step pipeline with caching end-to-end was the
priority. Scoring correctness (rubric-grounded, non-fabricated
reliability/relevance ratings) is subtle; we did not want to tune
parallelism and batching at the same time as hardening the scoring
contract.

**Strategic fix direction:**
Parallelize per-source scoring using threads (default; see
[`specs/execution-model.md`](specs/execution-model.md) R13). Batching
inside a single scorer call is likely a bad idea — batched prompts
tend to produce regressions in judgement quality — but parallel
per-source calls keep the prompt unchanged. File as a separate issue
when the parallelization sprint that currently owns PRs/branches
settles.

---

## TD-002 — `lxml` / `trafilatura` process-pool fallback for Step 5 fetch

**Status:** Active (workaround shipped in #128; migration still pending
per #124)
**Accepted:** before 2026-04-22 (pre-existing; workaround merged
2026-04-22 via PR #128)
**Tracking issue:** #124 (thread-safe migration); #128 is the PR that
shipped the process-parallel workaround
**Affects:** `src/diogenes/parallelize.py::parallelize_process`,
`src/diogenes/pipeline.py` (step_05 fetch site); conflicts with
[`specs/execution-model.md`](specs/execution-model.md) R13 and
[`specs/parallelization.md`](specs/parallelization.md) R1.

**What we accepted:**
Page fetch / content extraction is parallelized with a
`ProcessPoolExecutor` rather than threads. The underlying HTML parser
(`lxml` via `trafilatura`) is not thread-safe — contention produces
native SIGABRT crashes rather than Python exceptions. Shipping the
process-parallel path (PR #128) materially improves fetch wall time,
but it is still a workaround — the strategic fix is a thread-safe
extractor.

**Why we accepted it:**
A native crash in a parallel worker is fatal and silent-ish (pool
recovery is messy, data-loss risk is real). Threads would be cheaper
in memory and pickling cost, but not at the cost of native crashes.
Processes work reliably today.

**Strategic fix direction:**
Migrate to a thread-safe HTML parser / content extractor. Candidates
include selectolax, BeautifulSoup with a thread-safe parser backend,
or a fork/wrapper of trafilatura that avoids the unsafe paths. Issue
#124 stays open until migration completes — #128 merging does **not**
resolve #124.

---

## TD-001 — Print-based logging in place of structured logging

**Status:** Active
**Accepted:** before 2026-04-22 (pre-existing; recorded here)
**Tracking issue:** #104
**Affects:** Python layer pipeline logging; interacts with
[`specs/reliability-guarantees.md`](specs/reliability-guarantees.md)
R5–R8 (no silent failure; retries and fallbacks must be logged).

**What we accepted:**
The pipeline uses `print` statements (and minor variations) for
status and progress output rather than structured logging via the
`logging` module (or similar). Log output is human-oriented, lacks
consistent level/module/timestamp formatting, and is not
programmatically filterable.

**Why we accepted it:**
Early iteration needed visible progress in the terminal more than
it needed structured logs. The print approach was fast to write,
cheap to read during prompt-iteration loops, and kept the
dependency surface small.

**Strategic fix direction:**
Move to the stdlib `logging` module with a structured formatter
(JSON lines preferred), one module-level logger per module, log
levels that correspond to reliability-guarantee obligations
(retries at INFO, fallbacks at WARNING, R5–R7 violations at
ERROR). Keep the human-facing progress surface (CLI progress
bar) separate from the log stream — log-for-humans and
log-for-machines are different jobs.

## Resolved entries

## TD-003 — `/research` skill monolithic `SKILL.md` not yet a state machine

**Status:** Resolved (by PR #119, commit c4b1043, merged 2026-04-21)
**Accepted:** 2026-04-14
**Tracking issue:** #110 (closed by PR #119)
**Affects:** Plugin `/research` skill; now driven by the locked
[`specs/state-machine.md`](specs/state-machine.md).

**What we accepted:**
The `/research` skill was originally a single, large `SKILL.md` that
asked the AI coordinator to run the full pipeline, coupling coordinator
prompt, step descriptions, and error handling into one prompt blob.

**Why we accepted it:**
The 11-step pipeline was converging; rewriting the skill around a
state machine while the step contents themselves were still
stabilizing would have thrashed both. The monolithic form also made
end-to-end testing easier because every step lived in one file.

**Strategic fix direction:**
Decompose into a state-machine-driven coordinator where each node
owns one step's prompt, its input/output schema, its failure
semantics, and its tests.

**Resolution:**
PR #119 (commit c4b1043, `feat: state-machine-driven pipeline
orchestration (#110)`) landed the `state_machine.py` module with a
`PIPELINE_STEPS` registry and `StepDefinition` / `PipelineState`
classes. Both CLI and `/research` skill paths now drive the same
registry, diverging only at the execution layer (direct handler calls
vs MCP `dio_next_step` / `dio_execute_step`). The monolithic skill is
retired. [`specs/state-machine.md`](specs/state-machine.md) is now
Locked and describes the shipped system.

## Obsolete entries

_(none yet — entries move here when a deviation is reclassified
as acceptable-by-design or when the affected subsystem is
removed.)_
