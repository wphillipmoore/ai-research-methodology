# Reliability Guarantees

**Status:** Locked (baseline) — the correctness contracts the methodology
holds itself to. These requirements are first-principles and override any
cost, speed, or convenience argument that would weaken them. Relaxing a
MUST requires an explicit, tracked decision record.
**Last verified:** 2026-04-22 (contracts extracted from project memory,
incident history around feature/94 smoke-testing, and the prompt/pipeline
implementation).
**Sources:** `project_hallucination_mission`, `project_show_your_work_principle`,
`feedback_correctness_over_cost`, `feedback_failure_must_not_be_silent`,
`feedback_search_result_accountability`, `feedback_api_key_scoping`,
`feedback_100_percent_coverage`; pipeline implementation under
`src/diogenes/pipeline.py` and prompts under `src/diogenes/prompts/`.

## Purpose

This spec states the reliability contracts every part of the methodology
must satisfy. It exists because the methodology's entire value comes from
being **trustable**, and trustability in an AI-assisted pipeline is
obtained only by structural means. A pipeline that "usually" produces
correct output but occasionally fabricates is not a reliable pipeline;
it is a plausible one. Plausibility is explicitly not the goal.

The contracts below are organized into three groups: what the AI layer
must do (show its work), what the Python layer must do (check the work
and never fail silently), and what the system as a whole must do
(account for every input, log every failure, keep auditing cheap).

## Core principles

- **We do not trust the AI.** Every factual AI output must be checkable
  by Python after the call. Judgment stays in the model; verification
  stays in code.
- **Failure must not be silent.** A silently swallowed error in the
  Python layer becomes a fabrication in the AI layer downstream.
- **Correctness beats cost beats speed.** A cheap or fast wrong answer
  is strictly worse than an expensive or slow right one.
- **Auditability is a ceiling property, not an average property.** It
  applies to every output, not 95% of them.

## Requirements

### Group A — Show your work (AI layer contracts)

- **R1.** Every AI sub-agent whose output is consumed as fact MUST emit
  output that a deterministic Python check can verify after the fact.
  Acceptable check forms include (a) verbatim string match against
  a captured source, (b) JSON-schema validation with enumerated ranges
  / enums / required fields, (c) cross-reference to an ID from an
  earlier step. Narrative prose with no post-condition is not
  acceptable as a fact-bearing output.
- **R2.** The evidence-extractor MUST emit only verbatim excerpts from
  fetched source content. The Python coordinator MUST reject any
  excerpt that does not string-match against the source (see
  `_verify_packet_verbatim` in `src/diogenes/pipeline.py`).
- **R3.** Numeric AI outputs (relevance scores, reliability ratings,
  probability bands) MUST use enumerated ranges or schemas the
  validator can enforce. Free-form numeric output is not acceptable.
- **R4.** Synthesis steps (evidence synthesis, evaluator, self-audit)
  MUST cite the upstream artifact IDs (packet IDs, hypothesis IDs,
  scorecard IDs) whose content backs each synthesized claim, so the
  chain of custody remains machine-checkable.

### Group B — Never fail silently (Python layer contracts)

- **R5.** No caught exception in the Python layer MAY return an empty
  or default value without logging the failure and marking the
  affected record. Patterns like `except: return ""` or
  `except: pass` are prohibited outside of narrow, documented,
  test-covered boundary cases.
- **R6.** Operation outcomes MUST distinguish "succeeded with empty
  result" from "failed to execute." These MUST NOT collapse to the
  same return value. Structured return types (dataclasses, typed
  dicts, tuples, result objects) are preferred over sentinels.
- **R7.** When a fetch, a parse, a search, or any I/O operation fails,
  the downstream pipeline MUST either skip the record explicitly
  (with the skip recorded in the run's JSON output) or abort. It
  MUST NOT pass a substituted empty input to an AI sub-agent.
- **R8.** Retries, fallbacks, and partial successes MUST be logged in
  the run artifact. A reader MUST be able to tell from the archived
  JSON alone that a retry occurred, how many, and what the final
  outcome was.

### Group C — Full accountability (system-level contracts)

- **R9.** Every search result returned by the search layer MUST be
  dispositioned as either `selected` or `rejected`, each with a
  rationale. For every search step the invariant
  `len(selected) + len(rejected) == len(returned)` MUST hold and
  MUST be enforceable by Python.
- **R10.** Every source that was successfully fetched MUST appear in
  either the "scored" set or the "skipped" set of the run artifact,
  with a reason. Sources that vanish between fetch and synthesis
  are a reliability bug.
- **R11.** Every run MUST persist a methodology snapshot (prompts and
  schemas in force at run time). Reruns that use different prompts
  MUST be recognizable as such from the JSON alone.

### Group D — Credentials and configuration

- **R12.** `ANTHROPIC_API_KEY` MUST NOT be present in the general shell
  environment. It MUST be loaded from `dio`'s own configuration files
  (`.diorc`, `.env`, or equivalent) via `load_config()` at tool entry,
  so Claude Code's claude.ai auth is not displaced by a conflicting
  API key in the shell.
- **R13.** The only credential that MAY live in a global shell
  configuration is `GH_TOKEN` (or equivalent user-level, non-API-key
  credential). Per-service API keys MUST be service-scoped.
- **R14.** Missing or invalid credentials MUST produce a loud,
  actionable error at startup. Silent degradation (e.g., "falling
  back to unauthenticated search") is a R5 violation unless the
  fallback is explicitly logged and declared in the run JSON.

### Group E — Test coverage

- **R15.** All Python code in the methodology's reference
  implementation MUST maintain 100% line AND branch coverage, enforced
  in CI via `--cov-fail-under=100` for both lines and branches.
- **R16.** Code that genuinely cannot be reliably tested MAY be marked
  with an explicit coverage exception (e.g., `# pragma: no cover`),
  with justification in a comment. The remaining non-excepted code
  MUST still be 100%.
- **R17.** PRs that lower coverage below 100% (including by adding
  uncovered exception-handler branches) MUST NOT be merged without
  an accompanying exception or additional tests that restore
  coverage.

### Group F — Release discipline

- **R18.** A correctness bug (fabrication, silent failure, chain-of-
  custody break) MUST NOT be shipped behind a follow-up issue. The
  release is delayed until the correctness bug is fixed.
- **R19.** Cost optimizations that change verdicts relative to a
  reference configuration MUST be rejected. Token volume reductions
  (batching, caching, trimming) are preferred over model-quality
  downgrades.

## Enforcement surfaces

| Contract | Enforced where | Enforcement type |
|----------|----------------|------------------|
| R1 / R2 | `src/diogenes/pipeline.py` (`_verify_packet_verbatim`) | Runtime rejection of invalid packets |
| R3 | `src/diogenes/schemas/*.schema.json` + `schema_validator.py` | JSON Schema validation |
| R4 | Evaluator / self-auditor prompts; Python cross-check on IDs | Prompt constraint + Python cross-check |
| R5–R8 | Pipeline error paths, tests | Code review + tests |
| R9 | `search.py` result-selection routine | Runtime assertion |
| R10 | Pipeline source-scoring and synthesis gates | Runtime assertion |
| R11 | Setup step (methodology snapshot archival) | Pipeline setup |
| R12–R14 | `src/diogenes/config.py::load_config()` | Runtime validation at tool entry |
| R15–R17 | CI coverage gate | Pre-merge gate |
| R18–R19 | Release process | Human discipline (tracked in release notes) |

## Related specs

- [`research-methodology.md`](research-methodology.md) — top-level
  scope and supported modes
- [`workflow-architecture.md`](workflow-architecture.md) — where in the
  pipeline each contract applies
- [`output-contract.md`](output-contract.md) — what the JSON output
  artifact MUST contain to support these contracts
- [`../tech-debt-register.md`](../tech-debt-register.md) — accepted
  deviations from these contracts (with strategic-fix direction)
