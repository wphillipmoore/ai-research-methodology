# Output Contract

**Status:** Locked (baseline) — the external contract consumers may rely on.
Additive changes to the JSON artifact (new optional fields) are permitted
with a schema bump; breaking changes (renamed fields, removed fields,
tightened enums) require an explicit decision record and a spec update.
**Last verified:** 2026-04-22 (post-merge re-verification against
`src/diogenes/schemas/`, `src/diogenes/renderer.py`,
`src/diogenes/commands/run.py`, and `src/diogenes/state_machine.py`
after #93 / #110 / #117).
**Sources:** `project_json_first_architecture`,
`feedback_search_result_accountability`,
`feedback_failure_must_not_be_silent`; schemas under
`src/diogenes/schemas/` and rendering code in
`src/diogenes/renderer.py`. Per-instance state tracking
(`pipeline-state.json`, `usage.json`, `prompt-snapshot.md`) is
produced by `state_machine.py` and `commands/run.py`.

## Purpose

The output contract defines what a Diogenes run returns to callers: what
is in the JSON, what is in the Markdown, which is canonical, what fields
downstream consumers may rely on, and which invariants the system holds
across all outputs. This is the external-interface spec — anything
shipped in a run artifact is something we have committed to keeping
stable (or migrating explicitly).

## Principle: JSON is canonical, Markdown is a rendering

Every run produces a JSON artifact. Markdown outputs — drill-down
hierarchy, flat file, reading list — are deterministically rendered
from that JSON by pure Python. Consumers who need programmatic access
MUST use the JSON. Consumers who need human-readable output MUST use
the rendered Markdown. Reverse-parsing Markdown to reconstruct the JSON
is not supported.

## Requirements

### The canonical artifact

- **R1.** Every run MUST produce a JSON artifact that is schema-valid
  against the packaged schemas in `src/diogenes/schemas/`. Non-
  schema-valid output is a bug in the pipeline, not a consumer
  problem.
- **R2.** The JSON artifact MUST contain the input that was given
  (claim, query, or document reference), the clarified input, the
  hypotheses, the search plan, the selected and rejected search
  results with rationales, the fetched source scorecards, the
  evidence packets (if applicable to the run mode), the synthesis,
  the assessment, the self-audit, and the reading list.
- **R3.** The JSON artifact MUST carry a methodology snapshot
  identifier (prompt version, schema version, configuration hash)
  sufficient to tell which methodology produced the artifact. Two
  runs with different prompts MUST produce distinguishable
  artifacts.

### Markdown rendering

- **R4.** Markdown is produced by a pure-Python renderer
  (`src/diogenes/renderer.py::render_run`); no LLM tokens MUST be
  consumed to generate Markdown from JSON.
- **R5.** Rendering operates on a **single instance directory** —
  `dio render` always treats its input as a flat run dir. Group-
  level renderings (cross-instance synthesis, consistency,
  group-level reading list) are not produced.
- **R5a.** The renderer MUST support both (a) a **drill-down
  hierarchy** — a directory of linked Markdown files for interactive
  navigation, and (b) a **flat file** — a single consolidated
  document suitable for linear reading or publication-as-appendix.
- **R6.** Markdown renderings MUST include links back into the
  drill-down hierarchy from the flat file and forward links from
  summary rows to detail files in the drill-down form.

### Reading list (denormalization invariant)

- **R7.** Every run MUST produce a reading list of sources consulted.
- **R8.** Each reading-list entry MUST be self-contained at the
  Markdown rendering layer: it MUST denormalize title, authors,
  date, and content summary so a reader does not need a
  render-time join to understand the entry.
- **R9.** The reading list MUST reflect the actual sources
  contributing to the synthesis. A source that was fetched but
  excluded from synthesis (skipped, low-scored, or dropped for
  cause) MUST NOT appear in the reading list without an explicit
  marker of why it is listed.

### Search accountability

- **R10.** For every search step, the JSON artifact MUST include
  both the `selected` and `rejected` result lists, each with
  rationales, such that
  `len(selected) + len(rejected) == len(returned)`. Downstream
  consumers may rely on this invariant; pipeline implementations
  MUST enforce it (see
  [`reliability-guarantees.md`](reliability-guarantees.md) R9).

### Evidence packets

- **R11.** Evidence packets (`step_06_evidence_packets` output) MUST
  contain verbatim excerpts, the source scorecard ID they came from,
  the hypothesis ID(s) they relate to, and an explicit relation
  (`supports` / `refutes` / `nuances` / `context`).
- **R12.** Verbatim excerpts MUST be string-matchable against the
  captured `content_extract` of the source scorecard. Excerpts
  that do not match MUST be rejected by the coordinator before
  they reach synthesis (see
  [`reliability-guarantees.md`](reliability-guarantees.md) R2).

### Scorecards

- **R13.** A source scorecard MUST include reliability rating,
  relevance rating, bias domains, `content_extract`,
  `content_summary`, `authors`, `date`, and a list of checkable
  `items` (claims or sub-claims captured from the source), as
  declared in the schema.
- **R14.** The scorer prompt MUST NOT echo `title`, `snippet`, or
  `content_extract` back in its output — these fields are
  re-attached by Python after the scoring call to avoid
  transcription drift.

### Research container and per-instance state

- **R15.** A research container (parent `--output` directory) MUST
  preserve the user-supplied source input file unmodified at the
  parent level and MUST store each instance as a sibling
  subdirectory named `YYYY-MM-DD-HHMMSS/`. The pipeline MUST NOT
  write into the parent except to create new instance directories.
- **R16.** Each instance directory MUST contain (in addition to the
  per-step JSON output files):
  - `research-input-clarified.json` — `step_01` output (per-instance
    by design; re-clarification on rerun captures model drift);
  - `pipeline-state.json` — per-step status (`started_at`,
    `completed_at`, `elapsed_seconds`, retry counts);
  - `prompt-snapshot.md` — methodology snapshot of prompts in force
    at run time;
  - `usage.json` — per-step token, model, and cost data.
- **R16a.** The pipeline MUST NOT emit cross-instance synthesis,
  consistency, or diff artifacts. Group-level `synthesis.md`,
  `consistency.md`, and group reading-list outputs are explicitly
  retired (#93). Cross-instance comparison is a consumer concern.

### Cost and provenance

- **R17.** The JSON artifact MUST include per-step token counts
  (input and output) and the model that served each call. This is
  required to compute run cost without re-running.
- **R18.** The JSON artifact MUST include provenance for every
  non-deterministic piece of content: which sub-agent produced it,
  under which prompt version, at which timestamp.
- **R19.** Cache hits MUST be annotated in the JSON as such, per
  source, so a reader can distinguish freshly-computed from
  replayed scorecards.

### Stability

- **R20.** Adding a new optional field to a schema is a **non-breaking**
  change and MAY be made with a schema version bump.
- **R21.** Renaming, removing, or tightening an existing field
  (narrowing an enum, adding a required key, changing a type) is a
  **breaking** change and requires a decision record plus a schema
  major version bump.
- **R22.** The package MUST ship the canonical schemas under
  `src/diogenes/schemas/`; the reference copies under
  [`schemas/`](schemas/) exist for documentation only and MUST
  match the packaged versions.

### Rendering-only fields

- **R23.** Fields that exist solely to support rendering (navigation
  metadata, breadcrumbs, flat-file anchors) MAY vary between
  renderings and MUST NOT appear in the canonical JSON. They are
  computed by the renderer.

## Non-goals

- Cross-language schema generation. The JSON artifact is the contract;
  binding types in other languages is a consumer concern.
- Markdown that is reverse-parseable. The flat-file output optimizes
  for reading, not round-tripping.
- Streaming output. The JSON artifact is produced at end-of-run; partial
  artifacts during a run are internal.

## Related specs

- [`research-methodology.md`](research-methodology.md) — top-level
  scope and supported modes
- [`reliability-guarantees.md`](reliability-guarantees.md) — contracts
  the pipeline must satisfy to produce a trustworthy artifact
- [`execution-model.md`](execution-model.md) — per-path equivalence
  of JSON output
- [`workflow-architecture.md`](workflow-architecture.md) — where in
  the pipeline each artifact field originates
- [`schemas/`](schemas/) — canonical data contracts referenced above
