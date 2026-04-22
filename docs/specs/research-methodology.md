# Research Methodology

**Status:** Locked (baseline) — top-level spec for what Diogenes is and the
non-negotiable properties its output must have. Scope changes here (adding a
MUST, removing a MUST, changing a supported mode) require an explicit decision
record and a spec update before implementation.
**Last verified:** 2026-04-22 (post-merge re-verification against
`src/diogenes/state_machine.py`, `src/diogenes/commands/run.py`,
`src/diogenes/pipeline.py`, `src/diogenes/mcp_server.py`, and the
`/research` skill, after merges of #110 / #117 / #89 / #124 / #93 /
#131; see issue #129 for the spec-extraction effort this is part of).
**Sources:** `project_hallucination_mission`, `project_show_your_work_principle`,
`project_diogenes_current_state`, `project_diogenes_scope_vision`,
`project_multi_path_architecture`, `project_plugin_mcp_strategy`,
`feedback_correctness_over_cost`, `feedback_failure_must_not_be_silent`;
implementation under `src/diogenes/pipeline.py`, `src/diogenes/mcp_server.py`,
and prompts in `src/diogenes/prompts/`. Pipeline step-by-step flow is
specified in [`workflow-architecture.md`](workflow-architecture.md).

## Purpose

Diogenes is a research methodology and reference implementation for performing
claim verification, open-ended query answering, and document fact-checking with
an AI-in-the-loop pipeline whose outputs are **auditable**, not merely
plausible. The project's defining bet is that reliability in AI-assisted
research comes from forcing the model to "show its work" in forms that
deterministic Python code can check — and from rejecting any output that
fails those checks.

Tagline: "Diogenes walked through Athens with a lantern, searching for an
honest man. We're building the lantern."

## Scope

### In scope

- Claim verification ("is this claim supported by evidence?")
- Query answering ("what does the evidence say about this question?")
- Document fact-checking ("which statements in this document are supported,
  contradicted, or unsupported?")
- **Time-series comparison** of the same research against the same
  source input executed at different points in time (`dio rerun`
  produces a new timestamped **instance** inside the same
  **research container**; cross-instance comparison is a consumer
  concern — the pipeline does not synthesize across instances)
- Producing both machine-readable (JSON) and human-readable (Markdown)
  artifacts from every instance, suitable for archival and citation

### Out of scope

- Narrative journalism, editorial opinion, or persuasive writing
- Anything that produces a conclusion without a traceable evidence trail
- Real-time / low-latency question answering (the methodology prioritizes
  correctness over speed; see [`reliability-guarantees.md`](reliability-guarantees.md))
- Private-dataset analysis where the source corpus cannot be re-fetched
  and re-verified (the pipeline assumes public, re-fetchable sources)

## Supported modes

The three supported input modes map to three claim/query/document workflows
that share the same sub-agent pipeline described in
[`workflow-architecture.md`](workflow-architecture.md).

| Mode | Input | Output |
|------|-------|--------|
| Claim verification | A claim plus optional axioms | Per-claim evidence synthesis, probability assessment, reading list |
| Query answering | An open-ended question | Per-query synthesis organized by hypothesis, reading list |
| Document fact-check | A document (MD / PDF / URL) | Per-statement assessment for each checkable statement |

## Requirements

### Auditability and anti-hallucination

- **R1.** The system MUST produce outputs whose factual claims can be traced
  back to specific verbatim excerpts from specific sources. Paraphrase-only
  synthesis is prohibited.
- **R2.** The system MUST include a deterministic post-condition check for
  every sub-agent whose output is factual (see
  [`reliability-guarantees.md`](reliability-guarantees.md) R1–R4).
  Sub-agents that cannot meet this bar MUST either be redesigned to show
  their work or be removed from the pipeline.
- **R3.** The system MUST distinguish "no evidence found" from "evidence
  found and assessed." Silent substitution of empty or fabricated content
  is prohibited (see `reliability-guarantees.md` R3).
- **R4.** The evidence-extractor (Step 5b) MUST emit only verbatim excerpts
  that string-match against the fetched source content; non-matching
  excerpts MUST be rejected by the coordinator before they reach
  downstream synthesis.

### Output and archival

- **R5.** Every run MUST produce a JSON artifact that is the canonical,
  reproducible representation of the run's findings. Markdown output MUST
  be a rendering of that JSON (see [`output-contract.md`](output-contract.md)).
- **R6.** Every run MUST produce a reading list of the sources consulted,
  with enough denormalized metadata per entry (title, authors, date,
  summary) for the entry to stand alone.
- **R7.** Every run MUST archive the prompts, schemas, and configuration
  that were in force at run time (methodology snapshot), so the run can
  be reproduced or audited independently of the current state of the
  repository.

### Execution paths

- **R8.** The methodology MUST be usable from at least three execution
  paths sharing the same sub-agent prompts and JSON schemas
  (see [`execution-model.md`](execution-model.md) for the three paths
  and their shared components).
- **R9.** A run initiated on one path MUST produce JSON structurally
  identical to a run on any other path, given the same input, prompts,
  and schemas. Rendering output MAY differ between paths.

### Search and sources

- **R10.** Search execution SHOULD run in Python (deterministic mechanics)
  while result judgment (relevance, reliability, evidence extraction)
  runs in the model layer. Model-driven end-to-end search is a rejected
  approach on cost grounds (see `project_search_architecture_decision`).
- **R11.** Every search result that was returned by the search layer MUST
  be dispositioned as either `selected` or `rejected` with a rationale.
  `selected + rejected = returned`; silent drops are prohibited.
- **R12.** The system SHOULD support tiered source strategies: free default
  web search, curated academic sources, and user-configured premium
  sources (see `project_search_source_strategy`).

### Reproducibility and change tracking

- **R13.** The system MUST treat a `--output` directory as a **research
  container** holding one immutable source input and one or more
  timestamped **instance** subdirectories. `dio run` establishes the
  container; `dio rerun` adds a new instance. The `--runs` multi-run
  concept is removed: each invocation produces exactly one instance.
- **R14.** `dio rerun` MUST re-execute every pipeline step — including
  input clarification (`step_01`) — against the saved source input.
  Reusing a prior clarification across instances is prohibited,
  because clarifier output is a pipeline artifact subject to model
  drift, not part of the immutable research definition.
- **R14a.** Cross-instance comparison (diff across reruns,
  consistency analysis across instances, article-impact assessment)
  is **not** a pipeline responsibility in the current design. If a
  future design re-introduces cross-instance synthesis, the
  requirement belongs in a new spec section, not a revival of the
  removed N-run-group model.

### Cost and model selection

- **R15.** Model selection per step SHOULD minimize token cost while
  preserving correctness. A cheaper model that changes verdicts compared
  to a stronger model on the same input is **not** an acceptable
  optimization for that step (see `feedback_correctness_over_cost`).
- **R16.** The system SHOULD expose per-step token and cost accounting in
  the JSON output, so cost can be quantified and compared across runs,
  paths, and methodology revisions.

## Non-goals

- The methodology does not aim for "high accuracy on average." It aims for
  **auditable** accuracy: every claim the system makes must be either
  falsifiable against the cited evidence or explicitly flagged as
  synthesis.
- The methodology does not try to hide its sub-agent structure from the
  reader. The multi-step chain of custody (clarify → hypothesize → search
  → score → extract → synthesize → evaluate → audit) is the product, not
  an implementation detail.
- The methodology does not aim to be the cheapest way to answer a
  question. Cheap-and-wrong is the failure mode the project exists to
  fight.

## Related specs

- [`reliability-guarantees.md`](reliability-guarantees.md) — correctness
  contracts every step must satisfy
- [`execution-model.md`](execution-model.md) — the three supported
  execution paths and the N-run group semantics
- [`output-contract.md`](output-contract.md) — JSON-first external contract
- [`workflow-architecture.md`](workflow-architecture.md) — the pipeline,
  step by step
- [`schemas/`](schemas/) — canonical data contracts
- [`parallelization.md`](parallelization.md) (Draft) — parallel execution model
- [`state-machine.md`](state-machine.md) (Draft) — planned state-machine
  replacement for the current monolithic orchestration
